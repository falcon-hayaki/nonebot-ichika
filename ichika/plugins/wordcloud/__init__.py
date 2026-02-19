"""
词云插件
- 每条群消息记录到聊天历史（过滤链接/@）
- 每天 00:38 北京时间生成词云并推送到启用的群
配置文件: resources/wordcloud/group_enable.json -> [群ID, ...]
"""
import asyncio
import base64
import json
import logging
import os
import random
import re
import time
from pathlib import Path

import requests
import jieba
import numpy as np
from PIL import Image
from wordcloud import WordCloud, ImageColorGenerator

from nonebot import require, on_message, logger, get_bot
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Bot, MessageSegment, Message

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

from ichika.utils.fileio import read_lines, addline, clear_file

RESOURCE_PATH = Path(__file__).parent.parent.parent / "resources" / "wordcloud"
CHAT_HISTORY_DIR = RESOURCE_PATH / "chat_history"
WORDCLOUD_DIR = RESOURCE_PATH / "group_wordcloud"
GROUP_ENABLE_FILE = RESOURCE_PATH / "group_enable.json"
FONT_PATH = str(RESOURCE_PATH / "HarmonyOS.ttf")
MASK_PATH = RESOURCE_PATH / "masks" / "litchi_newyear.png"

CHAT_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
WORDCLOUD_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)


def _load_group_enable() -> list[int]:
    try:
        with GROUP_ENABLE_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


# ─── 颜色方案 ───────────────────────────────────────────────

COLOR_SCHEMES = {
    "sunset": ["#FF6B6B", "#FFE66D", "#FF8E53", "#FE4A49", "#F9844A"],
    "ocean": ["#00D4FF", "#0099CC", "#0066CC", "#003D99", "#5DADE2"],
    "forest": ["#2ECC71", "#27AE60", "#1ABC9C", "#16A085", "#52BE80"],
    "purple_dream": ["#9B59B6", "#8E44AD", "#AF7AC5", "#D2B4DE", "#BB8FCE"],
    "warm": ["#E74C3C", "#EC7063", "#F39C12", "#F8B739", "#E67E22"],
    "cool": ["#3498DB", "#5DADE2", "#85C1E9", "#AED6F1", "#2980B9"],
    "aurora": ["#A29BFE", "#6C5CE7", "#FD79A8", "#FDCB6E", "#00B894"],
    "candy": ["#FF6B9D", "#FFC93C", "#C3BEF7", "#A1EAFB", "#FFB6B9"],
}


def _get_color_func(scheme: str = "sunset"):
    colors = COLOR_SCHEMES.get(scheme, COLOR_SCHEMES["sunset"])

    def color_func(word=None, font_size=None, **kwargs):
        if font_size:
            idx = min(int((font_size / 100) * len(colors)), len(colors) - 1)
        else:
            idx = random.randint(0, len(colors) - 1)
        return colors[idx]

    return color_func


def _gen_wordcloud_sync(word_list_str: str, wordcloud_data: dict, img_path: str) -> None:
    wc = WordCloud(**wordcloud_data).generate(word_list_str)
    wc.to_file(img_path)


def _remove_abstract_content(text: str) -> str:
    if (text.startswith("{") and text.endswith("}")) or (text.startswith("<") and text.endswith(">")):
        return ""
    text = re.sub(r"https?://\S+|www\.\S+", "", text)
    if "@" in text:
        return ""
    return text.strip()


# ─── 聊天记录监听 ────────────────────────────────────────────

log_chat_matcher = on_message(priority=99, block=False)


@log_chat_matcher.handle()
async def handle_log_chat(bot: Bot, event: GroupMessageEvent) -> None:
    group_enable = _load_group_enable()
    if event.group_id not in group_enable:
        return
    if str(event.user_id) == bot.self_id:
        return

    text = event.get_plaintext()
    cleaned = _remove_abstract_content(text)
    if not cleaned:
        return

    hist_file = CHAT_HISTORY_DIR / f"{event.group_id}.txt"
    await addline(str(hist_file), cleaned + "\n")


# ─── 定时词云生成 ─────────────────────────────────────────────

@scheduler.scheduled_job("cron", hour=0, minute=38, timezone="Asia/Shanghai", id="wordcloud_daily")
async def gen_wordcloud_task() -> None:
    group_enable = _load_group_enable()
    if not group_enable:
        return

    try:
        bot = get_bot()
    except Exception:
        logger.warning("wordcloud: no bot, skip")
        return

    # 停用词
    stopwords: set[str] = set()
    try:
        resp = requests.get(
            "https://raw.githubusercontent.com/hoochanlon/cn_stopwords/main/baidu_stopwords.txt",
            timeout=10,
        )
        stopwords.update(line.strip() for line in resp.text.splitlines() if line.strip())
    except Exception as e:
        logger.warning(f"wordcloud: fetch stopwords failed: {e}")

    # Mask
    mask = None
    colors = None
    if MASK_PATH.exists():
        try:
            mask_image = Image.open(str(MASK_PATH))
            mask = np.array(mask_image)
            colors = ImageColorGenerator(mask)
        except Exception as e:
            logger.warning(f"wordcloud: load mask failed: {e}")

    for group_id in group_enable:
        hist_file = CHAT_HISTORY_DIR / f"{group_id}.txt"
        lock_file = CHAT_HISTORY_DIR / f"{group_id}.lock"
        STALE_SECONDS = 7200

        # 原子锁
        lock_created = False
        try:
            fd = os.open(str(lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            lock_created = True
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(str(lock_file)) > STALE_SECONDS:
                    lock_file.unlink(missing_ok=True)
                    fd = os.open(str(lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    os.close(fd)
                    lock_created = True
            except Exception:
                pass

        if not lock_created:
            continue

        try:
            text_list = []
            if hist_file.exists():
                text_list = await read_lines(str(hist_file))
            text_list = [t.strip() for t in text_list if t.strip()]

            if not text_list:
                try:
                    await bot.send_group_msg(group_id=group_id, message="本日你群一句正经话没有，服了")
                except Exception as e:
                    logger.warning(f"wordcloud: send msg failed group={group_id}: {e}")
            else:
                word_list_str = " ".join(text_list)
                img_path = str(WORDCLOUD_DIR / f"{group_id}.png")

                if mask is not None:
                    wc_data = dict(
                        background_color="white",
                        max_words=3000,
                        min_font_size=30,
                        max_font_size=500,
                        stopwords=stopwords,
                        mask=mask,
                        color_func=colors,
                        collocations=False,
                        font_path=FONT_PATH,
                        relative_scaling=0.5,
                        prefer_horizontal=0.8,
                        margin=2,
                        contour_width=2,
                        contour_color="#FF6B6B",
                    )
                else:
                    scheme = random.choice(list(COLOR_SCHEMES.keys()))
                    wc_data = dict(
                        background_color="white",
                        max_words=3000,
                        height=1080,
                        width=1920,
                        min_font_size=10,
                        max_font_size=150,
                        stopwords=stopwords,
                        color_func=_get_color_func(scheme),
                        collocations=False,
                        font_path=FONT_PATH,
                        relative_scaling=0.5,
                        prefer_horizontal=0.7,
                        margin=2,
                    )

                # 在线程池中运行同步图片生成（避免阻塞事件循环）
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, _gen_wordcloud_sync, word_list_str, wc_data, img_path)

                with open(img_path, "rb") as f:
                    img_b64 = base64.b64encode(f.read()).decode()

                caption = f"📊 今日词云已送达\n今日你群共聊了 {len(text_list)} 句话"
                msg = Message(
                    MessageSegment.text(caption)
                    + MessageSegment.image(f"base64://{img_b64}")
                )
                try:
                    await bot.send_group_msg(group_id=group_id, message=msg)
                except Exception as e:
                    logger.warning(f"wordcloud: send pic failed group={group_id}: {e}")

            if hist_file.exists():
                await clear_file(str(hist_file))

            await asyncio.sleep(10)

        except Exception:
            logger.exception(f"wordcloud: error group={group_id}")
        finally:
            lock_file.unlink(missing_ok=True)
