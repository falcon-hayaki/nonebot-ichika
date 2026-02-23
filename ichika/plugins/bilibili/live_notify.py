"""
Bilibili 直播开播/下播通知插件
每 60 秒检查一次订阅主播的直播状态，推送到对应群组
复用 subscribes.json（与动态推送共用订阅列表）
直播状态记录在 live_data.json
"""
import asyncio
from pathlib import Path
from typing import Optional

from nonebot import require, logger, get_bot
from nonebot.adapters.onebot.v11 import MessageSegment, Message

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

from ichika.config import get as cfg_get
from ichika.utils.bili_api_manager import BilibiliApiManager
from ichika.utils.fileio import read_json, write_json

RESOURCE_PATH = Path(__file__).parent.parent.parent / "resources" / "bili_dynamic"
SUBSCRIBES_FILE = RESOURCE_PATH / "subscribes.json"
LIVE_DATA_FILE = RESOURCE_PATH / "live_data.json"

_lock = asyncio.Lock()
_bm: Optional[BilibiliApiManager] = None


def _get_manager() -> Optional[BilibiliApiManager]:
    global _bm
    if _bm is None:
        sessdata = cfg_get("bilibili.sessdata")
        if not sessdata:
            return None
        config = {
            "sessdata": sessdata,
            "bili_jct": cfg_get("bilibili.bili_jct") or "",
            "buvid3": cfg_get("bilibili.buvid3") or "",
            "dedeuserid": cfg_get("bilibili.dedeuserid") or "",
        }
        try:
            _bm = BilibiliApiManager(config=config)
        except Exception as e:
            logger.error(f"BilibiliApiManager init failed: {e}")
    return _bm


@scheduler.scheduled_job("interval", seconds=60, id="bilibili_live_notify")
async def bilibili_live_notify_task() -> None:
    async with _lock:
        await _do_live_check()


async def _do_live_check() -> None:
    bm = _get_manager()
    if not bm:
        return

    try:
        subscribes: dict = await read_json(SUBSCRIBES_FILE) or {}
        live_data: dict = await read_json(LIVE_DATA_FILE) or {}
    except Exception as e:
        logger.error(f"bilibili live: read config failed: {e}")
        return

    if not subscribes:
        return

    try:
        bot = get_bot()
    except Exception:
        logger.warning("bilibili live: no bot, skip")
        return

    data_changed = False

    for uid_str, conf in subscribes.items():
        uid: int = int(uid_str)
        groups: list[int] = conf.get("groups", [])
        if not uid or not groups:
            continue

        # 获取 User 对象
        user_obj = bm.get_user(uid)

        # 获取用户信息（包含直播间状态）
        try:
            user_info_raw = await user_obj.get_user_info()
            relation_info_raw = await user_obj.get_relation_info()
            user_info = BilibiliApiManager.parse_user_info(user_info_raw, relation_info_raw)
        except Exception as e:
            logger.exception(f"bilibili live: get_user_info {uid} failed")
            continue

        uname = user_info.get("name", uid_str)
        current_live_status = user_info.get("live_status", 0)  # 0=未开播, 1=直播中, 2=轮播
        live_title = user_info.get("live_title", "")
        live_url = user_info.get("live_url", "")
        live_cover = user_info.get("live_cover", "")

        # 获取上一次记录的直播状态
        prev_status = live_data.get(uid_str, {}).get("live_status", None)

        # 更新记录
        live_data[uid_str] = {
            "live_status": current_live_status,
            "name": uname,
            "live_title": live_title,
            "live_url": live_url,
        }
        data_changed = True

        # 首次运行(prev_status is None)，不发送通知（仅记录当前状态）
        if prev_status is None:
            logger.info(f"bilibili live: initialize {uname}({uid}) live_status={current_live_status}")
            continue

        # 状态未变化，跳过
        if current_live_status == prev_status:
            continue

        # ===== 开播通知 =====
        if current_live_status == 1 and prev_status != 1:
            logger.info(f"bilibili live: {uname}({uid}) 开播 - {live_title}")
            summary = (
                f"{uname} 正在直播\n"
                f"标题：{live_title}\n"
                f"链接：{live_url}"
            )
            for group_id in groups:
                try:
                    msg = Message(MessageSegment.text(summary))
                    if live_cover:
                        msg += MessageSegment.image(live_cover)
                    await bot.send_group_msg(group_id=group_id, message=msg)
                except Exception as e:
                    logger.warning(f"bilibili live: send start notify failed group={group_id}: {e}")

        # ===== 下播通知 =====
        elif prev_status == 1 and current_live_status != 1:
            prev_title = live_data.get(uid_str, {}).get("live_title", "") or live_title
            logger.info(f"bilibili live: {uname}({uid}) 下播")
            summary = f"{uname} 下锅了"
            for group_id in groups:
                try:
                    msg = Message(MessageSegment.text(summary))
                    await bot.send_group_msg(group_id=group_id, message=msg)
                except Exception as e:
                    logger.warning(f"bilibili live: send stop notify failed group={group_id}: {e}")

        await asyncio.sleep(1)

    if data_changed:
        try:
            await write_json(LIVE_DATA_FILE, live_data)
        except Exception as e:
            logger.error(f"bilibili live: write data failed: {e}")
