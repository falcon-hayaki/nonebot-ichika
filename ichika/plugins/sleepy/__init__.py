"""
Hayaki 状态查询
触发词: #hayaki / hayaki状态 / hayaki似了没
"""
import httpx

from nonebot import on_keyword, logger
from nonebot.adapters.onebot.v11 import MessageEvent

sleepy_matcher = on_keyword({"#hayaki", "hayaki状态", "hayaki似了没"}, priority=10, block=True)

_SLEEPY_URL = "https://sleepy.hayaki.top/api/v1/status"


@sleepy_matcher.handle()
async def handle_sleepy(event: MessageEvent) -> None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(_SLEEPY_URL)
            resp.raise_for_status()
            data = resp.json()
        status = data.get("status", "未知")
        device = data.get("device_name") or ""
        tip = f"Hayaki 当前状态：{status}"
        if device:
            tip += f"（{device}）"
        await sleepy_matcher.send(tip)
    except Exception as e:
        logger.warning(f"sleepy query failed: {e}")
        await sleepy_matcher.send("查询失败，服务可能暂时不可用 >_<")
