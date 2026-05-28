"""
Bilibili 插件包
"""
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="Bilibili",
    description="Bilibili 视频查询、动态推送、直播通知",
    usage=(
        "BVxxx / bilibili.com/video/BVxxx  —— 查询视频信息\n"
        "动态推送：每 5 分钟检查订阅用户的新动态\n"
        "直播通知：每 60 秒检查订阅主播开播/下播状态"
    ),
)
from ichika.config import get as cfg_get

if cfg_get("bilibili.sessdata"):
    from . import timeline, get_video, live_notify

