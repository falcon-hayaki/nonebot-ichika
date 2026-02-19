"""
Bilibili 视频信息查询
触发: 发送 bilibili.com/video/BVxxx 链接或 BVxxx
"""
import re
from datetime import datetime
from dateutil import parser as dateutil_parser

from nonebot import on_regex, logger
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment, Message

from ichika.config import get as cfg_get
from ichika.utils.bili_api_manager import BilibiliApiManager
from ichika.utils.tz import SHA_TZ

_BV_URL_PATTERN = re.compile(r"https?://www\.bilibili\.com/video/(BV[a-zA-Z0-9_]+)")
_BV_PATTERN = re.compile(r"^BV[a-zA-Z0-9_]+$")

get_video_matcher = on_regex(
    r"(?:https?://www\.bilibili\.com/video/BV[a-zA-Z0-9_]+|^BV[a-zA-Z0-9_]+$)",
    priority=10, block=False
)

_bm = None


def _get_manager():
    global _bm
    if _bm is None:
        cookie = cfg_get("bilibili.cookie")
        if not cookie:
            return None
        try:
            _bm = BilibiliApiManager(cookie=cookie)
        except Exception as e:
            logger.error(f"BilibiliApiManager init failed: {e}")
    return _bm


@get_video_matcher.handle()
async def handle_get_video(event: GroupMessageEvent) -> None:
    bm = _get_manager()
    if not bm:
        return

    text = event.get_plaintext().strip()
    url_match = _BV_URL_PATTERN.search(text)
    bv_match = _BV_PATTERN.match(text)

    if url_match:
        bv = url_match.group(1)
    elif bv_match:
        bv = text
    else:
        return

    try:
        video_info_raw = await bm.get_video_info(bv)
        video_info = bm.parse_video_info(video_info_raw)
        pub_time = datetime.fromtimestamp(int(video_info["pubdate"])).strftime("%Y-%m-%d %H:%M:%S")
        t = (
            f"{video_info['up']} 发布于 {pub_time}\n"
            f"标题：{video_info['title']}\n"
            f"简介：{video_info['desc']}\n"
            f"观看：{video_info['view']}  弹幕：{video_info['danmaku']}  评论：{video_info['reply']}\n"
            f"点赞：{video_info['like']}  投币：{video_info['coin']}  收藏：{video_info['favorite']}"
        )
        pic_url = video_info.get("pic", "")
        try:
            if pic_url:
                await get_video_matcher.send(
                    Message(MessageSegment.image(pic_url) + MessageSegment.text("\n" + t))
                )
            else:
                await get_video_matcher.send(t)
        except Exception as e:
            logger.warning(f"bilibili get_video send failed: {e}")
    except Exception:
        logger.exception(f"get_video_info error bv={bv}")
