"""
Twitter 插件包
"""
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="Twitter",
    description="Twitter 推文解析及订阅推送，支持视频/GIF",
    usage=(
        "x.com/.../status/xxx  —— 解析并展示推文（附图/视频/GIF）\n"
        "定时推送：每 7 分钟检查订阅用户新推文并推送到群组"
    ),
)
from ichika.config import get as cfg_get

# 只有配置了 cookie 才注册相关功能
if cfg_get("twitter.twikit_cookie") or cfg_get("twitter.cookie"):
    from . import timeline, get_tweet
