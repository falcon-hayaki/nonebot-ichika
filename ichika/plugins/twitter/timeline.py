"""
Twitter (twikit) 定时时间线推送插件
每2分钟检查一次订阅用户的新推文，推送到对应群组
配置项（.env.prod）：
  TWITTER_TWIKIT_COOKIE=<cookie string>
  TWITTER_PROXY=http://127.0.0.1:7897   (可选)
"""
import asyncio
import json
import random
import re
from pathlib import Path
from ichika.utils.llm_translator import translate_tweet_text
from ichika.utils.media_processing import async_download_video
from datetime import datetime, timedelta
from typing import Optional

from nonebot import require, logger, get_bot
from nonebot.adapters.onebot.v11 import MessageSegment, Message

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

from ichika.config import get as cfg_get
from ichika.utils.twikit_manager import TwikitManager
from ichika.utils.fileio import read_json, write_json

RESOURCE_PATH = Path(__file__).parent.parent.parent / "resources" / "twitter_tl_twikit"
SUBSCRIBES_FILE = RESOURCE_PATH / "subscribes.json"
DATA_FILE = RESOURCE_PATH / "data.json"

# 同一接口的最小调用间隔（秒）
API_INTERVAL = 100
_last_call: dict[str, float] = {}
_lock = asyncio.Lock()

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


async def _rate_limit(key: str) -> None:
    """限速：同一 key 调用间隔至少 API_INTERVAL 秒"""
    now = datetime.now().timestamp()
    last = _last_call.get(key, 0)
    wait = API_INTERVAL - (now - last)
    if wait > 0:
        await asyncio.sleep(wait)
    _last_call[key] = datetime.now().timestamp()
async def _format_tweet(tweet_data: dict, user_info: dict) -> str:
    name = user_info.get("name", "")
    screen_name = user_info.get("screen_name", "")
    tweet_type = tweet_data.get("tweet_type", "default")
    text = tweet_data.get("text", "")

    if tweet_type == "retweet":
        rt = tweet_data.get("retweet_data", {})
        rt_user = rt.get("user_info", {})
        rt_data = rt.get("data", {})
        header = f"{name}(@{screen_name}) 转推了 {rt_user.get('name', '')}(@{rt_user.get('screen_name', '')})"
        body = rt_data.get("text", "")
    elif tweet_type == "quote":
        q = tweet_data.get("quote_data", {})
        q_user = q.get("user_info", {})
        q_data = q.get("data", {})
        header = f"{name}(@{screen_name}) 引用了 {q_user.get('name', '')}(@{q_user.get('screen_name', '')})"
        body = f"{text}\n\n【原推】{q_data.get('text', '')}"
    else:
        header = f"{name}(@{screen_name}) 发推了"
        body = text

    tweet_id = tweet_data.get("id", "")
    url = f"\nhttps://x.com/{screen_name}/status/{tweet_id}" if tweet_id else ""
    
    # 获取翻译内容
    body_translated = await translate_tweet_text(body)
    
    # 只有在成功翻译、文本发生变化、且未产生“抱歉”或空字符串的异常回复时，才拼接翻译
    if body_translated and body_translated != body and not body_translated.startswith("抱歉"):
        body = f"{body}\n\n【翻译】\n{body_translated}"
        
    return f"{header}\n{body}{url}"


@scheduler.scheduled_job("interval", minutes=7, id="twitter_twikit_timeline")
async def twitter_twikit_timeline_task() -> None:
    async with _lock:
        await _do_timeline()


async def _do_timeline() -> None:
    tm = _get_manager()
    if not tm:
        return

    try:
        subscribes: dict = await read_json(SUBSCRIBES_FILE) or {}
        data: dict = await read_json(DATA_FILE) or {}
    except Exception as e:
        logger.error(f"twitter_twikit: read config failed: {e}")
        return

    if not subscribes:
        return

    try:
        bot = get_bot()
    except Exception:
        logger.warning("twitter_twikit: no bot, skip")
        return

    data_changed = False

    for screen_name, conf in subscribes.items():
        groups: list[int] = conf.get("groups", [])
        if not screen_name or not groups:
            continue

        # 获取用户信息
        try:
            await _rate_limit(f"user_info:{screen_name}")
            user_info = await tm.get_user_info(screen_name)
        except Exception as e:
            logger.warning(f"twitter_twikit: get_user_info {screen_name} failed: {e}")
            continue

        if not user_info:
            continue

        uid = user_info["id"]

        # 更新用户信息缓存
        user_cache = data.setdefault("users", {})
        user_cache[screen_name] = user_info
        data_changed = True

        # 获取时间线
        try:
            await _rate_limit(f"timeline:{uid}")
            timeline = await tm.get_user_timeline(uid, count=20)
        except Exception as e:
            logger.warning(f"twitter_twikit: get_timeline {screen_name} failed: {e}")
            continue

        if not timeline:
            continue

        # 找出新推文（对比已知 last_tweet_id）
        last_id = data.get("last_tweet_id", {}).get(screen_name, "")
        new_tweets = []

        for tid, tweet_data in sorted(timeline.items()):
            if last_id and tid <= last_id:
                continue
            new_tweets.append((tid, tweet_data))

        if not new_tweets:
            continue

        # 更新 last_tweet_id 为最新一条，无论是否推送
        latest_id = max(t[0] for t in new_tweets)
        data.setdefault("last_tweet_id", {})[screen_name] = latest_id
        data_changed = True

        # 过滤超过 10 分钟的旧推文
        now_ts = datetime.now().timestamp()
        valid_tweets = []
        for tid, tweet_data in new_tweets:
            created_at = tweet_data.get("created_at", "")
            try:
                # "Fri Oct 20 12:34:56 +0000 2023"
                dt = datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y")
                ts = dt.timestamp()
                if now_ts - ts > 600:  # 10分钟 = 600秒
                    continue
            except Exception:
                pass
            valid_tweets.append((tid, tweet_data))
            
        if not valid_tweets:
            continue

        # 推送到各群
        for tid, tweet_data in valid_tweets:
            msg_text = await _format_tweet(tweet_data, user_info)
            
            tweet_type = tweet_data.get("tweet_type", "default")
            imgs: list[str] = tweet_data.get("imgs", [])
            videos: list[str] = tweet_data.get("videos", [])

            if tweet_type == "retweet":
                rt_data = tweet_data.get("retweet_data", {}).get("data", {})
                imgs = rt_data.get("imgs", imgs)
                videos = rt_data.get("videos", videos)

            # 下载该推文的视频（最多4个）
            local_videos = []
            if videos:
                proxy = cfg_get("twitter.proxy")
                for video_url in videos[:4]:
                    logger.info(f"timeline 提取到视频链接: {video_url[:120]}")
                    local_path = await async_download_video(video_url, proxy=proxy)
                    if local_path:
                        logger.info(f"timeline 视频下载成功，加入待发送列表: {local_path}")
                        local_videos.append(local_path)
                    else:
                        logger.warning(f"timeline 视频下载失败，跳过: {video_url[:120]}")

            try:
                for group_id in groups:
                    if imgs or local_videos:
                        msg = Message(MessageSegment.text(msg_text))
                        for img_url in imgs[:4]:  # 最多发4张
                            msg += MessageSegment.image(img_url)
                        await bot.send_group_msg(group_id=group_id, message=msg)
                        for local_path in local_videos:
                            await bot.send_group_msg(group_id=group_id, message=Message(MessageSegment.video(local_path)))
                    else:
                        await bot.send_group_msg(group_id=group_id, message=msg_text)
            except Exception as e:
                logger.warning(f"twitter_twikit: send to group failed: {e}")
        
        # 每个用户处理完后随机等待，大幅降低频率
        await asyncio.sleep(random.randint(20, 40))

    if data_changed:
        try:
            await write_json(DATA_FILE, data)
        except Exception as e:
            logger.error(f"twitter_twikit: write data failed: {e}")
