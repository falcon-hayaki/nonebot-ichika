"""
YouTube 直播/视频定时推送插件
每 5 分钟检查一次订阅频道的直播状态，推送到对应群组
配置项（.env.prod）：
  YOUTUBE_API_KEY=<your api key>
"""
import asyncio
from pathlib import Path
from typing import Optional

from nonebot import require, logger, get_bot
from nonebot.adapters.onebot.v11 import MessageSegment, Message
from dateutil import parser as dateutil_parser

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

from ichika.config import get as cfg_get
from ichika.utils.youtube_manager import YoutubeManager
from ichika.utils.fileio import read_json, write_json
from ichika.utils.tz import SHA_TZ

RESOURCE_PATH = Path(__file__).parent.parent.parent / "resources" / "ytb_live_stream"
SUBSCRIBES_FILE = RESOURCE_PATH / "subscribes.json"
DATA_FILE = RESOURCE_PATH / "data.json"

_lock = asyncio.Lock()
_ym: Optional[YoutubeManager] = None

VIDEO_TYPE_TRANS = {
    "none": "视频",
    "live": "直播",
    "upcoming": "直播预约",
}


def _get_manager() -> Optional[YoutubeManager]:
    global _ym
    if _ym is None:
        api_key = cfg_get("youtube.api_key")
        if not api_key:
            return None
        try:
            _ym = YoutubeManager(api_key=api_key)
        except Exception as e:
            logger.error(f"YoutubeManager init failed: {e}")
    return _ym


@scheduler.scheduled_job("interval", minutes=5, id="ytb_live_stream")
async def ytb_live_stream_task() -> None:
    async with _lock:
        await _do_ytb()


async def _do_ytb() -> None:
    ym = _get_manager()
    if not ym:
        return

    try:
        subscribes: dict = await read_json(SUBSCRIBES_FILE) or {}
        data: dict = await read_json(DATA_FILE) or {}
    except Exception as e:
        logger.error(f"ytb: read config failed: {e}")
        return

    if not subscribes:
        return

    try:
        bot = get_bot()
    except Exception:
        logger.warning("ytb: no bot, skip")
        return

    data_changed = False

    for ident, conf in subscribes.items():
        groups: list[int] = conf.get("groups", [])
        if not ident or not groups:
            continue
        
        # 临时占位，防止 AttributeError
        # TODO: 实现完整的 Youtube 直播检查逻辑
        # try:
        #     channel_id = ident
        #     if "@" in ident:
        #          # handle -> channel_id logic
        #          pass
        #     # API call
        # except Exception as e:
        #     logger.warning(f"ytb: {ident} failed: {e}")
        
        await asyncio.sleep(0.1)

    if data_changed:
        try:
            await write_json(DATA_FILE, data)
        except Exception as e:
            logger.error(f"ytb: write data failed: {e}")
