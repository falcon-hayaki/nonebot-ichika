"""
帮我选插件
触发词: 帮我选 / !c
用法: 帮我选 选项1 选项2 选项3
"""
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="帮我选",
    description="帮你从多个选项中随机选择一个",
    usage=(
        "帮我选 选项1 选项2 ...  —— 随机选一个（空格或顿号分隔）\n"
        "!c 选项1 选项2 ...    —— 同上"
    ),
)
import random
import re

from nonebot import on_regex
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent

choose_matcher = on_regex(r"^(帮我选|!c)\s+(.+)", priority=10, block=True)


@choose_matcher.handle()
async def handle_help_choose(event: MessageEvent) -> None:
    text = event.get_plaintext().strip()
    match = re.match(r"^(?:帮我选|!c)\s+(.+)", text)
    if not match:
        return
    options_raw = match.group(1)
    # 支持空格或中文顿号分隔
    options = re.split(r"[\s　、]+", options_raw.strip())
    options = [o for o in options if o]
    if not options:
        return
    chosen = random.choice(options)
    await choose_matcher.send(f"我选择：{chosen}")
