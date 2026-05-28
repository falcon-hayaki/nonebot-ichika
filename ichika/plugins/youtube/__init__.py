"""
YouTube 插件包
"""
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="YouTube",
    description="YouTube 视频信息查询及直播通知",
    usage=(
        "youtube.com/watch?v=xxx / youtu.be/xxx  —— 查询视频信息\n"
        "直播通知：每 5 分钟检查订阅频道直播状态"
    ),
)
from ichika.config import get as cfg_get

if cfg_get("youtube.api_key"):
    from . import timeline, get_video
