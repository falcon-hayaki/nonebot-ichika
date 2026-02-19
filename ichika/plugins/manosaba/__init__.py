"""
魔法裁判贴图生成器
触发: 魔裁 <角色名> <内容> / manosaba <角色名> <内容>
"""
import base64
import os
import random
import re
from pathlib import Path

from nonebot import on_regex, logger
from nonebot.adapters.onebot.v11 import MessageEvent, MessageSegment, Bot

from .manosaba_plugin import (
    generate_image_with_text,
    get_character_id_by_nickname,
    get_random_expression,
    get_available_characters,
)

RESOURCE_PATH = Path(__file__).parent.parent.parent / "resources" / "manosaba"
OUT_DIR = RESOURCE_PATH / "out"

manosaba_matcher = on_regex(r"^(?:魔裁|manosaba)\s+(\S+)\s+(.+)", flags=re.DOTALL, priority=10, block=True)


@manosaba_matcher.handle()
async def handle_manosaba(event: MessageEvent) -> None:
    text = event.get_plaintext().strip()
    match = re.match(r"^(?:魔裁|manosaba)\s+(\S+)\s+(.+)", text, re.DOTALL)
    if not match:
        return

    nickname, content = match.group(1), match.group(2)

    if nickname in ["随机", "随便", "任意", "random"]:
        character_id = random.choice(get_available_characters())
    else:
        character_id = get_character_id_by_nickname(nickname)

    if not character_id:
        await manosaba_matcher.finish(f"找不到角色「{nickname}」，请检查名字或昵称")
        return

    try:
        background_index = random.randint(0, 15)
        expression_index = get_random_expression(character_id)

        png_bytes = generate_image_with_text(
            base_dir=str(RESOURCE_PATH),
            character_name=character_id,
            text=content,
            background_index=background_index,
            expression_index=expression_index,
        )

        OUT_DIR.mkdir(parents=True, exist_ok=True)
        pic_path = OUT_DIR / f"{event.user_id}.png"
        with open(pic_path, "wb") as f:
            f.write(png_bytes)

        img_b64 = base64.b64encode(png_bytes).decode()
        await manosaba_matcher.send(MessageSegment.image(f"base64://{img_b64}"))

    except Exception:
        logger.exception("manosaba error")
