"""
定时签到插件
每天 00:05 北京时间向指定群发送"签到"
"""
from nonebot import require, logger, get_bot

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

# 签到群列表
CHECKIN_GROUPS = [1014696092, 856337734]


# @scheduler.scheduled_job("cron", hour=0, minute=5, timezone="Asia/Shanghai", id="checkin_daily")
# async def checkin_daily() -> None:
#     try:
#         bot = get_bot()
#     except Exception:
#         logger.warning("checkin: no bot connected, skip")
#         return

#     for group_id in CHECKIN_GROUPS:
#         try:
#             await bot.send_group_msg(group_id=group_id, message="签到")
#         except Exception as e:
#             logger.warning(f"checkin failed for group {group_id}: {e}")
