"""
Twitter (twikit) 获取单条推文
触发: 发送 x.com/... 或 twitter.com/... 链接
配置: 同 timeline.py
"""
import re
from typing import Optional

from nonebot import on_regex, logger
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment, Message

from ichika.config import get as cfg_get
from ichika.utils.twikit_manager import TwikitManager
from ichika.utils.llm_translator import translate_tweet_text
from ichika.utils.media_processing import async_download_video

_URL_PATTERN = re.compile(
    r"https?://(?:x\.com|twitter\.com)/\w+/status/(\d+)"
)

get_tweet_matcher = on_regex(_URL_PATTERN.pattern, priority=10, block=False)

_tm: Optional[TwikitManager] = None


def _get_manager() -> Optional[TwikitManager]:
    global _tm
    if _tm is None:
        cookie = cfg_get("twitter.twikit_cookie") or cfg_get("twitter.cookie")
        if not cookie:
            return None
        proxy = cfg_get("twitter.proxy")
        config = {"cookie": cookie}
        if proxy:
            config["proxy"] = proxy
        try:
            _tm = TwikitManager(config=config)
        except Exception as e:
            logger.error(f"TwikitManager init failed: {e}")
    return _tm


@get_tweet_matcher.handle()
async def handle_get_tweet(event: GroupMessageEvent) -> None:
    tm = _get_manager()
    if not tm:
        return

    text = event.get_plaintext()
    match = _URL_PATTERN.search(text)
    if not match:
        return

    tweet_id = match.group(1)
    try:
        tweet_data, user_info = await tm.get_tweet_detail(tweet_id)
    except Exception as e:
        logger.warning(f"get_tweet_by_twikit failed {tweet_id}: {e}")
        return

    if not tweet_data or not user_info:
        return

    name = user_info.get("name", "")
    screen_name = user_info.get("screen_name", "")
    tweet_type = tweet_data.get("tweet_type", "default")
    tweet_text = tweet_data.get("text", "")
    imgs: list[str] = tweet_data.get("imgs", [])
    videos: list[str] = tweet_data.get("videos", [])

    if tweet_type == "retweet":
        rt = tweet_data.get("retweet_data", {})
        rt_user = rt.get("user_info", {})
        rt_data = rt.get("data", {})
        header = f"{name}(@{screen_name}) 转推了 {rt_user.get('name')}(@{rt_user.get('screen_name')})"
        body = rt_data.get("text", "")
        imgs = rt_data.get("imgs", imgs)
        videos = rt_data.get("videos", videos)
    elif tweet_type == "quote":
        q = tweet_data.get("quote_data", {})
        q_user = q.get("user_info", {})
        q_data = q.get("data", {})
        header = f"{name}(@{screen_name}) 引用了 {q_user.get('name')}(@{q_user.get('screen_name')})"
        body = f"{tweet_text}\n\n【原推】{q_data.get('text', '')}"
    else:
        header = f"{name}(@{screen_name})"
        body = tweet_text

    # 获取翻译内容
    body_translated = await translate_tweet_text(body)
    
    if body_translated and body_translated != body and not body_translated.startswith("抱歉"):
        body = f"{body}\n\n【翻译】\n{body_translated}"
        
    summary = f"{header}\n{body}"

    # 视频：先下载到本地
    local_videos = []
    proxy = cfg_get("twitter.proxy")
    for video_url in videos[:4]:
        logger.info(f"get_tweet 提取到视频链接: {video_url[:120]}")
        local_path = await async_download_video(video_url, proxy=proxy)
        if local_path:
            logger.info(f"get_tweet 视频下载成功，加入待发送列表: {local_path}")
            local_videos.append(local_path)
        else:
            logger.warning(f"get_tweet 视频下载失败，跳过: {video_url[:120]}")

    msg = Message(MessageSegment.text(summary))
    for img_url in imgs[:4]:
        msg += MessageSegment.image(img_url)

    try:
        await get_tweet_matcher.send(msg)
        for local_path in local_videos:
            await get_tweet_matcher.send(MessageSegment.video(local_path))
    except Exception as e:
        logger.warning(f"get_tweet send failed: {e}")
