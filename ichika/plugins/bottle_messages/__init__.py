"""
漂流瓶插件
扔漂流瓶: 扔漂流瓶 <内容>（可附图片）
捡漂流瓶: 捡漂流瓶
"""
import base64
import json
import logging
from datetime import datetime

import httpx
from nonebot import on_fullmatch, on_startswith, logger
from nonebot.adapters.onebot.v11 import (
    Bot, GroupMessageEvent, MessageSegment
)

from ichika.db.db import db

throw_matcher = on_startswith("扔漂流瓶", priority=10, block=True)
pick_matcher = on_fullmatch("捡漂流瓶", priority=10, block=True)


@throw_matcher.handle()
async def handle_throw(bot: Bot, event: GroupMessageEvent) -> None:
    text = event.get_plaintext().replace("扔漂流瓶", "", 1).strip()
    imgs_b64 = []

    # 收集图片
    for seg in event.message:
        if seg.type == "image":
            url = seg.data.get("url")
            if url:
                try:
                    async with httpx.AsyncClient(timeout=15) as client:
                        r = await client.get(url)
                        imgs_b64.append(base64.b64encode(r.content).decode())
                except Exception as e:
                    logger.warning(f"bottle image download failed: {e}")

    if not text and not imgs_b64:
        await throw_matcher.finish("漂流瓶是空的！请附上文字或图片")
        return

    member_info = await bot.get_group_member_info(group_id=event.group_id, user_id=event.user_id)
    user_name = member_info.get("nickname", str(event.user_id))

    db.insert_data(
        "bottle_messages",
        user_id=event.user_id,
        user_name=user_name,
        group_id=event.group_id,
        group_name="",
        text=text,
        imgs=json.dumps(imgs_b64, ensure_ascii=False),
        time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    await throw_matcher.send("漂流瓶已扔出~ 🍾")


@pick_matcher.handle()
async def handle_pick(event: GroupMessageEvent) -> None:
    row = db.random_bottle_message(event.group_id, event.user_id)
    if not row:
        await pick_matcher.finish("海面上没有漂流瓶，下次再来试试吧 🌊")
        return

    msg_parts = []
    user_name = row.get("user_name", "某人")
    time_str = row.get("time", "")
    text = row.get("text", "")

    header = f"🍾 捡到来自【{user_name}】的漂流瓶"
    if time_str:
        header += f"（{time_str}）"
    msg_parts.append(MessageSegment.text(header + "\n"))

    if text:
        msg_parts.append(MessageSegment.text(text))

    imgs_raw = row.get("imgs", "[]")
    try:
        imgs = json.loads(imgs_raw) if isinstance(imgs_raw, str) else imgs_raw
    except Exception:
        imgs = []

    for img_b64 in imgs:
        msg_parts.append(MessageSegment.image(f"base64://{img_b64}"))

    from nonebot.adapters.onebot.v11 import Message as Msg
    final_msg = Msg()
    for part in msg_parts:
        final_msg += part

    await pick_matcher.send(final_msg)
