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

    if tweet_type == "retweet":
        rt = tweet_data.get("retweet_data", {})
        rt_user = rt.get("user_info", {})
        rt_data = rt.get("data", {})
        summary = (
            f"{name}(@{screen_name}) 转推了 "
            f"{rt_user.get('name')}(@{rt_user.get('screen_name')})\n"
            f"{rt_data.get('text', '')}"
        )
        imgs = rt_data.get("imgs", imgs)
    elif tweet_type == "quote":
        q = tweet_data.get("quote_data", {})
        q_user = q.get("user_info", {})
        q_data = q.get("data", {})
        summary = (
            f"{name}(@{screen_name}) 引用了 "
            f"{q_user.get('name')}(@{q_user.get('screen_name')})\n"
            f"{tweet_text}\n\n【原推】{q_data.get('text', '')}"
        )
    else:
        summary = f"{name}(@{screen_name})\n{tweet_text}"

    msg = Message(MessageSegment.text(summary))
    for img_url in imgs[:4]:
        msg += MessageSegment.image(img_url)

    try:
        await get_tweet_matcher.send(msg)
    except Exception as e:
        logger.warning(f"get_tweet send failed: {e}")
