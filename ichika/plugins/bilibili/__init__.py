"""
Bilibili 插件包
"""
from ichika.config import get as cfg_get

if cfg_get("bilibili.cookie"):
    from . import timeline, get_video
