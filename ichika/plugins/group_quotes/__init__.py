"""
群友语录插件
/save <key> [图片]  —— 保存图片语录，key 为自定义关键字
/quote <key>       —— 随机调出某 key 对应的一条语录
"""
import base64
import json
import logging
from datetime import datetime

from nonebot import on_command, logger
from nonebot.adapters.onebot.v11 import (
    Bot, GroupMessageEvent, MessageSegment, Message
)
from nonebot.params import CommandArg

from ichika.db.db import db

logger = logging.getLogger(__name__)

save_matcher = on_command("save", priority=10, block=True)
quote_matcher = on_command("quote", priority=10, block=True)


@save_matcher.handle()
async def handle_save(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()) -> None:
    # 提取 key（命令后的文本参数）
    key = args.extract_plain_text().strip()
    if not key:
        await save_matcher.finish("用法：/save <key> [图片]\n例如：/save xh [图片]")
        return

    # 优先从当前消息中找图片
    img_url = None
    for seg in event.message:
        if seg.type == "image":
            img_url = seg.data.get("url")
            break

    # 如果当前消息没有图片，检查是否回复了一条带图片的消息
    if not img_url:
        reply_msg_id = None
        for seg in event.message:
            if seg.type == "reply":
                reply_msg_id = seg.data.get("id")
                break

        if reply_msg_id:
            try:
                orig_msg_data = await bot.get_msg(message_id=int(reply_msg_id))
                orig_msg = Message(orig_msg_data.get("message", []))
                for seg in orig_msg:
                    if seg.type == "image":
                        img_url = seg.data.get("url")
                        break
            except Exception as e:
                logger.warning(f"get_msg failed: {e}")

    if not img_url:
        await save_matcher.finish("请附带一张图片，或回复一条包含图片的消息")
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

    group_id = event.group_id
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.insert_data("quotes", user_key=key, group_id=group_id, img=img_b64, time=now_str)
    await save_matcher.send(f"已保存语录")


@quote_matcher.handle()
async def handle_quote(event: GroupMessageEvent, args: Message = CommandArg()) -> None:
    # 提取 key
    key = args.extract_plain_text().strip()
    if not key:
        await quote_matcher.finish("用法：/quote <key>\n例如：/quote xh")
        return

    group_id = event.group_id
    row = db.random_quote(group_id, key)

    if not row:
        await quote_matcher.finish(f"还没有 [{key}] 的语录")
        return

    img_b64 = row["img"]
    await quote_matcher.send(
        MessageSegment.text(f"[{key}] 的语录：\n")
        + MessageSegment.image(f"base64://{img_b64}")
    )
