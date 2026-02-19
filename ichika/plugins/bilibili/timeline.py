"""
Bilibili 动态定时推送插件
每 5 分钟检查一次订阅用户的新动态，推送到对应群组
配置项（.env.prod）：
  BILIBILI_SESSDATA=
  BILIBILI_BILI_JCT=
  BILIBILI_BUVID3=
  BILIBILI_DEDEUSERID=
"""
import asyncio
from pathlib import Path
from typing import Optional
from datetime import datetime

from nonebot import require, logger, get_bot
from nonebot.adapters.onebot.v11 import MessageSegment, Message

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

from ichika.config import get as cfg_get
from ichika.utils.bili_api_manager import BilibiliApiManager
from ichika.utils.fileio import read_json, write_json

RESOURCE_PATH = Path(__file__).parent.parent.parent / "resources" / "bili_dynamic"
SUBSCRIBES_FILE = RESOURCE_PATH / "subscribes.json"
DATA_FILE = RESOURCE_PATH / "data.json"

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


@scheduler.scheduled_job("interval", minutes=5, id="bilibili_dynamic_timeline")
async def bilibili_dynamic_task() -> None:
    async with _lock:
        await _do_dynamic()


async def _do_dynamic() -> None:
    bm = _get_manager()
    if not bm:
        return

    try:
        subscribes: dict = await read_json(SUBSCRIBES_FILE) or {}
        data: dict = await read_json(DATA_FILE) or {}
    except Exception as e:
        logger.error(f"bilibili: read config failed: {e}")
        return

    if not subscribes:
        return

    try:
        bot = get_bot()
    except Exception:
        logger.warning("bilibili: no bot, skip")
        return

    data_changed = False

    for uid_str, conf in subscribes.items():
        uid: int = int(uid_str)
        groups: list[int] = conf.get("groups", [])
        if not uid or not groups:
            continue

        # 获取 User 对象
        user_obj = bm.get_user(uid)

        # 获取用户信息
        try:
            user_info_raw = await user_obj.get_user_info()
            relation_info_raw = await user_obj.get_relation_info()
            user_info = BilibiliApiManager.parse_user_info(user_info_raw, relation_info_raw)
        except Exception as e:
            logger.warning(f"bilibili: get_user_info {uid} failed: {e}")
            continue

        data.setdefault("users", {})[uid_str] = user_info
        data_changed = True

        # 获取动态列表
        try:
            dynamic_raw = await user_obj.get_dynamics_new()
            dynamic_id_list, dynamics = BilibiliApiManager.parse_timeline(dynamic_raw)
        except Exception as e:
            logger.warning(f"bilibili: get_dynamic {uid} failed: {e}")
            continue

        if not dynamic_id_list:
            continue

        # 找出新动态
        last_id = data.get("last_dynamic_id", {}).get(uid_str, "")
        new_ids = [did for did in dynamic_id_list if not last_id or did > last_id]

        if not new_ids:
            continue

        latest_id = max(new_ids)
        data.setdefault("last_dynamic_id", {})[uid_str] = latest_id
        data_changed = True

        # 过滤超过 10 分钟的旧动态
        now_ts = datetime.now().timestamp()
        valid_ids = []
        for did in new_ids:
            dyn = dynamics.get(did, {})
            ts = int(dyn.get("time", 0))
            if now_ts - ts > 600:
                continue
            valid_ids.append(did)
        
        if not valid_ids:
            continue

        uname = user_info.get("name", uid_str)
        for did in valid_ids:
            dyn = dynamics.get(did, {})
            text = dyn.get("text", "")
            imgs: list[str] = dyn.get("imgs", [])
            links: list[str] = dyn.get("links", [])
            unknown = dyn.get("unknown_type", "")

            if unknown:
                summary = f"📢 {uname} 发布了新动态（类型：{unknown}）"
            else:
                summary = f"📢 {uname} 发布了新动态\n{text}"
                if links:
                    summary += "\n" + "\n".join(l for l in links if l)

            try:
                for group_id in groups:
                    msg = Message(MessageSegment.text(summary))
                    for img_url in imgs[:4]:
                        msg += MessageSegment.image(img_url)
                    await bot.send_group_msg(group_id=group_id, message=msg)
            except Exception as e:
                logger.warning(f"bilibili: send failed group={group_id}: {e}")

        await asyncio.sleep(2)

    if data_changed:
        try:
            await write_json(DATA_FILE, data)
        except Exception as e:
            logger.error(f"bilibili: write data failed: {e}")
