"""
Twitter 插件包
"""
from ichika.config import get as cfg_get

# 只有配置了 cookie 才注册相关功能
if cfg_get("twitter.twikit_cookie") or cfg_get("twitter.cookie"):
    from . import timeline, get_tweet
