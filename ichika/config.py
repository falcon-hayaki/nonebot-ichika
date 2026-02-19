"""
公共配置加载模块
从 NoneBot2 driver config 中读取各服务的配置项
对应 botoy 的 jconfig.get('key')
"""
from nonebot import get_driver

_config = None


def _get_config():
    global _config
    if _config is None:
        _config = get_driver().config
    return _config


def get(key: str, default=None):
    """读取配置项，key 用点号分隔（如 'twitter.cookie'），会转换为下划线形式"""
    cfg = _get_config()
    # 'twitter.cookie' -> 'twitter_cookie'
    attr = key.replace('.', '_').lower()
    return getattr(cfg, attr, default)
