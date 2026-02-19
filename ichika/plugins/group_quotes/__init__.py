"""
群友语录插件
/save @某人  —— 保存当前被引用消息为语录（需有图片）
/quote @某人 —— 随机调出某人的一条语录
"""
import base64
import json
import logging
from datetime import datetime

from nonebot import on_command, logger
from nonebot.adapters.onebot.v11 import (
    Bot, GroupMessageEvent, MessageSegment, Message
)

from ichika.db.db import db

logger = logging.getLogger(__name__)

save_matcher = on_command("save", priority=10, block=True)
quote_matcher = on_command("quote", priority=10, block=True)


@save_matcher.handle()
async def handle_save(bot: Bot, event: GroupMessageEvent) -> None:
    # 获取被回复的消息（reply segment）
    reply_msg_id = None
    for seg in event.message:
        if seg.type == "reply":
            reply_msg_id = seg.data.get("id")
            break

    # 获取 @ 对象
    at_user = None
    for seg in event.message:
        if seg.type == "at":
            at_user = int(seg.data.get("qq", 0))
            break

    if not reply_msg_id or not at_user:
        await save_matcher.finish("用法：/save @某人（需回复一条包含图片的消息）")
        return

    # 获取原始消息内容
    try:
        orig_msg_data = await bot.get_msg(message_id=int(reply_msg_id))
    except Exception as e:
        logger.warning(f"get_msg failed: {e}")
        await save_matcher.finish("获取原消息失败")
        return

    # 找图片
    orig_msg = Message(orig_msg_data.get("message", []))
    img_url = None
    for seg in orig_msg:
        if seg.type == "image":
            img_url = seg.data.get("url")
            break

    if not img_url:
        await save_matcher.finish("原消息中没有图片，无法保存语录")
        return

    # 下载图片转 base64
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(img_url)
            img_b64 = base64.b64encode(r.content).decode()
    except Exception as e:
        logger.warning(f"download image failed: {e}")
        await save_matcher.finish("图片下载失败，请稍后再试")
        return

    user_key = str(at_user)
    group_id = event.group_id
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.insert_data("quotes", user_key=user_key, group_id=group_id, img=img_b64, time=now_str)
    await save_matcher.send(f"已保存 {at_user} 的语录 ✓")


@quote_matcher.handle()
async def handle_quote(event: GroupMessageEvent) -> None:
    # 获取 @ 对象
    at_user = None
    for seg in event.message:
        if seg.type == "at":
            at_user = int(seg.data.get("qq", 0))
            break

    if not at_user:
        await quote_matcher.finish("用法：/quote @某人")
        return

    user_key = str(at_user)
    group_id = event.group_id
    row = db.random_quote(group_id, user_key)

    if not row:
        await quote_matcher.finish(f"还没有 {at_user} 的语录")
        return

    img_b64 = row["img"]
    await quote_matcher.send(
        MessageSegment.at(at_user)
        + MessageSegment.image(f"base64://{img_b64}")
    )
