"""
私聊重定向插件
功能：收到私聊消息时回复引导文字，用户可选择退订
触发: 所有私聊消息（排除自身）
"""
import json
from pathlib import Path

from nonebot import on_message, logger
from nonebot.adapters.onebot.v11 import PrivateMessageEvent, Bot
from nonebot.rule import Rule

RESOURCE_PATH = Path(__file__).parent.parent.parent / "resources" / "redirection"
SKIP_USERS_FILE = RESOURCE_PATH / "skip_users.json"


def _load_skip_users() -> list[int]:
    try:
        with SKIP_USERS_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_skip_users(users: list[int]) -> None:
    RESOURCE_PATH.mkdir(parents=True, exist_ok=True)
    with SKIP_USERS_FILE.open("w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False)


redirection_matcher = on_message(priority=20)


@redirection_matcher.handle()
async def handle_redirection(bot: Bot, event: PrivateMessageEvent) -> None:
    user_id = event.user_id
    # 排除自身消息（bot 的 QQ）
    if str(user_id) == bot.self_id:
        return

    skip_users = _load_skip_users()
    if user_id in skip_users:
        return

    text = event.get_plaintext().strip()
    if text in ["TD", "td", "退订", "不再提醒"]:
        skip_users.append(user_id)
        _save_skip_users(skip_users)
        await redirection_matcher.send("退订成功")
    else:
        await redirection_matcher.send(
            "ハーロー、イチカっすよ～\n有任何问题请加群183914156联系群主\n回复「不再提醒」忽略该消息"
        )
