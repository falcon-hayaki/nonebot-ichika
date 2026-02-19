"""
测试/调试插件
- 关键词「一花」→ 回复「ここっすよ～」（任意场景）
- 调试群（1014696092）内有图片的消息 → 原样转发（用于测试图片发送）
"""
import base64
import logging

import httpx
from nonebot import on_fullmatch, on_message, logger
from nonebot.adapters.onebot.v11 import (
    Bot, GroupMessageEvent, MessageEvent, MessageSegment, Message,
)
from nonebot.rule import Rule

logger = logging.getLogger(__name__)

DEBUG_GROUP = 1014696092

# ─── hello ──────────────────────────────────────────────────────

hello_matcher = on_fullmatch("一花", priority=5, block=False)


@hello_matcher.handle()
async def handle_hello(bot: Bot, event: MessageEvent) -> None:
    text = event.get_plaintext()
    logger.info(f"Test plugin received: {text}")
    
    # 过滤自身消息
    if str(event.user_id) == bot.self_id:
        return
    await hello_matcher.send("ここっすよ～")


# ─── debug（只在调试群生效）──────────────────────────────────────

def _is_debug_group(event: GroupMessageEvent) -> bool:
    return event.group_id == DEBUG_GROUP


debug_matcher = on_message(Rule(_is_debug_group), priority=99, block=False)


@debug_matcher.handle()
async def handle_debug(bot: Bot, event: GroupMessageEvent) -> None:
    if str(event.user_id) == bot.self_id:
        return

    # 找出消息中的图片
    img_segs = [seg for seg in event.message if seg.type == "image"]
    
    if not img_segs:
        # 无图片：记录 raw 消息数据，方便调试
        logger.info("debug text from %s: %s", event.user_id, event.get_plaintext())
        return

    # 有图片：下载后原样转发（测试 base64 发送路径）
    img_b64_list: list[str] = []
    async with httpx.AsyncClient(timeout=15) as client:
        for seg in img_segs:
            url = seg.data.get("url", "")
            if not url:
                continue
            try:
                r = await client.get(url)
                img_b64_list.append(base64.b64encode(r.content).decode())
            except Exception as e:
                logger.warning(f"debug: download image failed: {e}")
                await debug_matcher.send(f"图片下载失败：{e}")
                return

    text = event.get_plaintext()
    msg = Message(MessageSegment.text(text)) if text else Message()
    for b64 in img_b64_list:
        msg += MessageSegment.image(f"base64://{b64}")

    try:
        await bot.send_group_msg(group_id=event.group_id, message=msg)
    except Exception as e:
        logger.exception(f"debug: send_group_msg failed: {e}")
