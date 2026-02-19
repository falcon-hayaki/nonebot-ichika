"""
YouTube 插件包
"""
from ichika.config import get as cfg_get

if cfg_get("youtube.api_key"):
    from . import timeline, get_video
