''' 媒体文件处理 '''
import requests
import base64
import logging
import tempfile
import os
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# 视频临时文件目录
_VIDEO_TEMP_DIR = Path(tempfile.gettempdir()) / "ichika_video_cache"
_VIDEO_TEMP_DIR.mkdir(parents=True, exist_ok=True)


def download_from_url_and_convert_to_base64(url):
    response = requests.get(url)
    if response.status_code == 200:
        image_base64 = base64.b64encode(response.content).decode()
        return 200, image_base64
    else:
        logger.error("下载失败，状态码: %s", response.status_code)
        return response.status_code, response.text


async def async_download_video(
    url: str,
    proxy: Optional[str] = None,
    timeout: float = 60.0,
) -> Optional[str]:
    """
    异步下载视频到临时文件，返回 file:// 路径。
    如果下载失败返回 None。

    Parameters
    ----------
    url : 视频直链 (mp4)
    proxy : HTTP 代理地址，例如 http://127.0.0.1:7897
    timeout : 下载超时时间（秒）
    """
    try:
        logger.info(f"开始下载视频: {url[:120]}...")
        async with httpx.AsyncClient(
            proxy=proxy,
            timeout=httpx.Timeout(timeout),
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()

            content_length = len(resp.content)
            logger.info(f"视频下载完成, 大小: {content_length / 1024 / 1024:.2f}MB")

            if content_length == 0:
                logger.warning("视频内容为空")
                return None

            # 写入临时文件
            fd, tmp_path = tempfile.mkstemp(
                suffix=".mp4", dir=str(_VIDEO_TEMP_DIR)
            )
            try:
                os.write(fd, resp.content)
            finally:
                os.close(fd)

            file_uri = f"file://{tmp_path}"
            logger.info(f"视频已保存到: {tmp_path}")
            return file_uri

    except httpx.TimeoutException:
        logger.warning(f"视频下载超时: {url[:120]}")
        return None
    except httpx.HTTPStatusError as e:
        logger.warning(f"视频下载HTTP错误 {e.response.status_code}: {url[:120]}")
        return None
    except Exception as e:
        logger.warning(f"视频下载失败: {e}")
        return None


def cleanup_video_cache(max_age_seconds: int = 3600) -> None:
    """清理过期的视频缓存文件"""
    import time
    now = time.time()
    try:
        for f in _VIDEO_TEMP_DIR.iterdir():
            if f.is_file() and (now - f.stat().st_mtime) > max_age_seconds:
                f.unlink(missing_ok=True)
    except Exception as e:
        logger.warning(f"清理视频缓存失败: {e}")