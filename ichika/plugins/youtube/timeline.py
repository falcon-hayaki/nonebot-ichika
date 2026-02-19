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
        subscribes: list[dict] = await read_json(SUBSCRIBES_FILE) or []
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

    for sub in subscribes:
        channel_id: str = sub.get("channel_id", "")
        groups: list[int] = sub.get("groups", [])
        if not channel_id or not groups:
            continue

        try:
            code, result = ym.get_channel_live_status(channel_id)
            if code != 0 or not result:
                continue
        except Exception as e:
            logger.warning(f"ytb: get_channel_live_status {channel_id} failed: {e}")
            continue

        # result 是最新视频/直播信息
        vid = result.get("videoId", "")
        live_type = result.get("liveBroadcastContent", "none")

        prev = data.get("last_video", {}).get(channel_id, {})
        prev_vid = prev.get("videoId", "")
        prev_type = prev.get("liveBroadcastContent", "")

        # 更新缓存
        data.setdefault("last_video", {})[channel_id] = result
        data_changed = True

        # 判断是否需要推送
        should_notify = False
        if vid != prev_vid:
            should_notify = True  # 新视频
        elif live_type != prev_type and live_type in ("live", "upcoming"):
            should_notify = True  # 状态变化

        if not should_notify:
            continue

        name = result.get("name", channel_id)
        title = result.get("title", "")
        type_str = VIDEO_TYPE_TRANS.get(live_type, live_type)
        published_at = result.get("publishedAt", "")
        thumbnail = result.get("thumbnail", "")

        try:
            pub_str = dateutil_parser.parse(published_at).astimezone(SHA_TZ).strftime("%Y-%m-%d %H:%M:%S %Z") if published_at else ""
        except Exception:
            pub_str = published_at

        text = f"📺 {name} 的{type_str}\n发布于：{pub_str}\n标题：{title}"
        if vid:
            text += f"\nhttps://www.youtube.com/watch?v={vid}"

        try:
            for group_id in groups:
                if thumbnail:
                    msg = Message(MessageSegment.image(thumbnail) + MessageSegment.text("\n" + text))
                else:
                    msg = Message(text)
                await bot.send_group_msg(group_id=group_id, message=msg)
        except Exception as e:
            logger.warning(f"ytb: send failed: {e}")

        await asyncio.sleep(1)

    if data_changed:
        try:
            await write_json(DATA_FILE, data)
        except Exception as e:
            logger.error(f"ytb: write data failed: {e}")
