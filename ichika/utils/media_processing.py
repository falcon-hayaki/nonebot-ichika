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
    suffix: str = ".mp4",
) -> Optional[str]:
    """
    异步下载视频到临时文件，返回本地文件路径（不含 file:// 前缀）。
    如果下载失败返回 None。

    Parameters
    ----------
    url : 视频直链 (mp4)
    proxy : HTTP 代理地址，例如 http://127.0.0.1:7897
    timeout : 下载超时时间（秒）
    suffix : 临时文件后缀，默认 .mp4
    """
    if not proxy:
        proxy = None
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
                suffix=suffix, dir=str(_VIDEO_TEMP_DIR)
            )
            try:
                os.write(fd, resp.content)
            finally:
                os.close(fd)

            logger.info(f"视频已保存到: {tmp_path}")
            return tmp_path

    except httpx.TimeoutException:
        logger.warning(f"视频下载超时: {url[:120]}")
        return None
    except httpx.HTTPStatusError as e:
        logger.warning(f"视频下载HTTP错误 {e.response.status_code}: {url[:120]}")
        return None
    except Exception as e:
        logger.warning(f"视频下载失败: {e}")
        return None


async def async_convert_mp4_to_gif(
    mp4_path: str,
    fps: int = 15,
    scale: int = 480,
) -> Optional[str]:
    """
    使用 ffmpeg 将 mp4 文件转换为 GIF，返回 GIF 文件的本地路径。
    采用两步调色板法获得更好的画质。
    如果转换失败返回 None。

    Parameters
    ----------
    mp4_path : 本地 mp4 文件路径
    fps : GIF 帧率，默认 15
    scale : GIF 宽度（像素），高度等比缩放，默认 480
    """
    import asyncio

    gif_path = mp4_path.replace(".mp4", ".gif")
    palette_path = mp4_path.replace(".mp4", "_palette.png")

    try:
        # 第一步：生成调色板
        palette_cmd = [
            "ffmpeg", "-y",
            "-i", mp4_path,
            "-vf", f"fps={fps},scale={scale}:-1:flags=lanczos,palettegen",
            palette_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *palette_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.warning(f"ffmpeg 生成调色板失败: {stderr.decode()[-500:]}")
            return None

        # 第二步：用调色板渲染 GIF
        gif_cmd = [
            "ffmpeg", "-y",
            "-i", mp4_path,
            "-i", palette_path,
            "-filter_complex", f"fps={fps},scale={scale}:-1:flags=lanczos[x];[x][1:v]paletteuse",
            gif_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *gif_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.warning(f"ffmpeg 转换 GIF 失败: {stderr.decode()[-500:]}")
            return None

        logger.info(f"GIF 转换成功: {gif_path}")
        return gif_path

    except FileNotFoundError:
        logger.warning("ffmpeg 未安装，无法转换 GIF")
        return None
    except Exception as e:
        logger.warning(f"GIF 转换异常: {e}")
        return None
    finally:
        # 清理调色板临时文件
        try:
            if os.path.exists(palette_path):
                os.unlink(palette_path)
        except Exception:
            pass


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