"""
Bilibili 动态定时推送插件
每 5 分钟检查一次订阅用户的新动态，推送到对应群组
配置项（.env.prod）：
  BILIBILI_COOKIE=<cookie string>
"""
import asyncio
import re
from pathlib import Path
from typing import Optional

from nonebot import require, logger, get_bot
from nonebot.adapters.onebot.v11 import MessageSegment, Message

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

from ichika.config import get as cfg_get
from ichika.utils.bili_api_manager import BilibiliApiManager
from ichika.utils.fileio import read_json, write_json

RESOURCE_PATH = Path(__file__).parent.parent.parent / "resources" / "bili_dynamic"
SUBSCRIBES_FILE = RESOURCE_PATH / "subscribes.json"
DATA_FILE = RESOURCE_PATH / "data.json"

_lock = asyncio.Lock()
_bm: Optional[BilibiliApiManager] = None


def _get_manager() -> Optional[BilibiliApiManager]:
    global _bm
    if _bm is None:
        cookie = cfg_get("bilibili.cookie")
        if not cookie:
            return None
        try:
            _bm = BilibiliApiManager(cookie=cookie)
        except Exception as e:
            logger.error(f"BilibiliApiManager init failed: {e}")
    return _bm


@scheduler.scheduled_job("interval", minutes=5, id="bilibili_dynamic_timeline")
async def bilibili_dynamic_task() -> None:
    async with _lock:
        await _do_dynamic()


async def _do_dynamic() -> None:
    bm = _get_manager()
    if not bm:
        return

    try:
        subscribes: list[dict] = await read_json(SUBSCRIBES_FILE) or []
        data: dict = await read_json(DATA_FILE) or {}
    except Exception as e:
        logger.error(f"bilibili: read config failed: {e}")
        return

    if not subscribes:
        return

    try:
        bot = get_bot()
    except Exception:
        logger.warning("bilibili: no bot, skip")
        return

    data_changed = False

    for sub in subscribes:
        uid: str = str(sub.get("uid", ""))
        groups: list[int] = sub.get("groups", [])
        if not uid or not groups:
            continue

        try:
            user_info_raw = await bm.get_user_info(uid)
            user_info = bm.parse_user_info(user_info_raw)
        except Exception as e:
            logger.warning(f"bilibili: get_user_info {uid} failed: {e}")
            continue

        if not user_info:
            continue

        data.setdefault("users", {})[uid] = user_info
        data_changed = True

        try:
            dynamic_raw = await bm.get_user_dynamic(uid)
            dynamics = bm.parse_dynamic(dynamic_raw)
        except Exception as e:
            logger.warning(f"bilibili: get_dynamic {uid} failed: {e}")
            continue

        if not dynamics:
            continue

        last_id = data.get("last_dynamic_id", {}).get(uid, "")
        new_items = [(did, d) for did, d in sorted(dynamics.items()) if not last_id or did > last_id]

        if not new_items:
            continue

        latest_id = max(t[0] for t in new_items)
        data.setdefault("last_dynamic_id", {})[uid] = latest_id
        data_changed = True

        uname = user_info.get("name", uid)
        for did, dyn in new_items:
            dyn_type = dyn.get("type", "")
            content = dyn.get("content", "")
            img_url = dyn.get("img", "")
            summary = f"📢 {uname} 发布了新动态\n{content}"

            try:
                for group_id in groups:
                    if img_url:
                        msg = Message(MessageSegment.text(summary) + MessageSegment.image(img_url))
                    else:
                        msg = Message(summary)
                    await bot.send_group_msg(group_id=group_id, message=msg)
            except Exception as e:
                logger.warning(f"bilibili: send failed: {e}")
        
        await asyncio.sleep(2)

    if data_changed:
        try:
            await write_json(DATA_FILE, data)
        except Exception as e:
            logger.error(f"bilibili: write data failed: {e}")
