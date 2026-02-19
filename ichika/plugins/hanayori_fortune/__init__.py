"""
花より运势 (Hanayori Fortune) 插件
触发词: 抽签 / 抽签签
"""
import base64
import json
import random
from datetime import datetime
from pathlib import Path

from nonebot import on_keyword, logger
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Bot, MessageSegment

from .draw import Draw

# 资源路径：项目根目录下统一的 resources 文件夹
# __file__ = ichika/plugins/hanayori_fortune/__init__.py
# .parent * 3 = 项目根
RESOURCE_PATH = Path(__file__).parent.parent.parent / "resources" / "hanayori_fortune"

fortune_matcher = on_keyword({"抽签", "抽签签"}, priority=10, block=True)


@fortune_matcher.handle()
async def handle_fortune(bot: Bot, event: GroupMessageEvent) -> None:
    # 读取文案和运势类型文件
    copywriting_path = RESOURCE_PATH / "fortune" / "copywriting.json"
    good_luck_path = RESOURCE_PATH / "fortune" / "goodLuck.json"

    with copywriting_path.open("r", encoding="utf-8") as f:
        texts_data = json.load(f)
    with good_luck_path.open("r", encoding="utf-8") as f:
        titles_data = json.load(f)

    # 用日期+用户QQ作为随机种子，保证同一天结果相同
    now = datetime.now()
    user_id = event.user_id
    seed = int("".join(str(i) for i in [now.year, now.month, now.day, user_id]))

    random.seed(seed)
    choice = random.choice(range(1, 12))   # 卡面编号 1-11
    random.seed(seed)
    text_entry = random.choice(texts_data["copywriting"])

    # 找对应的运势类型名称
    title = ""
    for title_entry in titles_data["types_of"]:
        if title_entry["good-luck"] == text_entry["good-luck"]:
            title = title_entry["name"]
            break

    text = text_entry["content"]
    pic_chosen = str(RESOURCE_PATH / "img" / f"frame_{choice}.png")

    # 生成图片（用群组ID + 用户ID 区分文件，避免多群同时抽签冲突）
    pic_path = await Draw.draw_card(RESOURCE_PATH, pic_chosen, title, text, user_id)
    if not pic_path:
        logger.warning("hanayori_fortune: draw_card returned None, text may be too long")
        await fortune_matcher.finish("签文太长了，抽不出来喵 >_<")
        return

    # 读取图片转 base64
    with open(pic_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    msg = (
        MessageSegment.at(user_id)
        + MessageSegment.text(" 今天的运势是\n")
        + MessageSegment.image(f"base64://{img_b64}")
    )
    await fortune_matcher.send(msg)
