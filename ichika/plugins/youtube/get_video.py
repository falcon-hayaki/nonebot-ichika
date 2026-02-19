"""
YouTube 视频信息查询
触发: 发送 youtube.com/watch?v=xxx 或 youtu.be/xxx 链接
"""
import re

from nonebot import on_regex, logger
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment, Message
from dateutil import parser as dateutil_parser

from ichika.config import get as cfg_get
from ichika.utils.youtube_manager import YoutubeManager
from ichika.utils.tz import SHA_TZ

_YTB_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]+)"
)
VIDEO_TYPE_TRANS = {"none": "视频", "live": "直播", "upcoming": "直播预约"}

get_ytb_matcher = on_regex(_YTB_PATTERN.pattern, priority=10, block=False)

_ym = None


def _get_manager():
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


@get_ytb_matcher.handle()
async def handle_get_ytb(event: GroupMessageEvent) -> None:
    ym = _get_manager()
    if not ym:
        return

    text = event.get_plaintext()
    match = _YTB_PATTERN.search(text)
    if not match:
        return

    vid = match.group(1)
    try:
        code, res = ym.get_video_details(vid)
        if code != 0 or not res:
            await get_ytb_matcher.send("获取视频信息失败")
            return

        pub_str = ""
        try:
            pub_str = dateutil_parser.parse(res["publishedAt"]).astimezone(SHA_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
        except Exception:
            pub_str = res.get("publishedAt", "")

        type_str = VIDEO_TYPE_TRANS.get(res.get("liveBroadcastContent", "none"), "视频")
        summary = (
            f"📺 {res.get('name', '')} 的{type_str}\n"
            f"发布于：{pub_str}\n"
            f"标题：{res.get('title', '')}"
        )
        thumbnail = res.get("thumbnail", "")

        if thumbnail:
            msg = Message(MessageSegment.image(thumbnail) + MessageSegment.text("\n" + summary))
        else:
            msg = Message(summary)

        await get_ytb_matcher.send(msg)
    except Exception:
        logger.exception(f"get_ytb_video error vid={vid}")
        await get_ytb_matcher.send("获取视频信息时发生错误")
