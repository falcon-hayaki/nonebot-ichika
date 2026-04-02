from nonebot import on_command, require
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, MessageSegment, Message
from nonebot.typing import T_State
from nonebot.params import CommandArg
from nonebot.log import logger
import httpx
import base64

from ichika.config import get as cfg_get

# 注册命令
receipt_cmd = on_command("一花小票", priority=5, block=True)

PROMPT_TEXT = (
    "这是一张我在海外旅行时的购物小票。请识别出小票上的所有内容，将商品名称翻译为中文，并以此格式输出：\n"
    "商品名(原文) - 商品名(中文翻译) - 价格\n"
    "如果有额外的折扣或税费也请列出。\n"
    "最后请统计出总金额。\n"
    "直接输出整理好的账单结果，不需要任何额外的闲聊或解释。"
)

@receipt_cmd.handle()
async def _(bot: Bot, event: MessageEvent, state: T_State, args: Message = CommandArg()):
    img_urls = []
    
    if event.reply:
        for seg in event.reply.message:
            if seg.type == "image" and seg.data.get("url"):
                img_urls.append(seg.data.get("url"))

    for seg in event.message:
        if seg.type == "image" and seg.data.get("url"):
            img_urls.append(seg.data.get("url"))
            
    if not img_urls:
        await receipt_cmd.finish("请发送带有小票图片的指令（如发文本「/一花小票」附加上图片，或者对小票图片回复「/一花小票」）")

    target_img_url = img_urls[0]
    
    api_key = cfg_get("gemini_api_key")
    if not api_key:
        await receipt_cmd.finish("未配置 Gemini API Key，请在 .env 中设置 GEMINI_API_KEY。")
        
    await receipt_cmd.send("正在识别翻译小票，请稍候...")

    try:
        # 防呆，有些 URL 没有 scheme
        if target_img_url.startswith("//"):
            target_img_url = "http:" + target_img_url

        # 1. 下载图片并转为 base64
        async with httpx.AsyncClient(timeout=30.0) as client:
            img_resp = await client.get(target_img_url)
            img_resp.raise_for_status()
            img_bytes = img_resp.content
            mime_type = img_resp.headers.get("content-type", "image/jpeg")
            if not mime_type or mime_type == "application/octet-stream":
                # Fallback based on simple checks if needed, but normally QQ gives correct mime
                mime_type = "image/jpeg"
                
            img_base64 = base64.b64encode(img_bytes).decode("utf-8")
        
        # 2. 调用 Gemini API
        gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={api_key}"
        
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": PROMPT_TEXT},
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": img_base64
                            }
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 1500,
            }
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(gemini_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            
            try:
                result_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                if result_text:
                    await receipt_cmd.finish(result_text)
                else:
                    await receipt_cmd.finish("未能从小票中提取并翻译出有效内容。")
            except (KeyError, IndexError):
                logger.error(f"receipt_assistant: Gemini API returned unexpected format: {data}")
                await receipt_cmd.finish(f"小票识别解析失败，模型返回的格式异常: {data}")
                
    except httpx.HTTPStatusError as e:
        logger.error(f"receipt_assistant: HTTP Error: {e.response.text}")
        await receipt_cmd.finish("识别失败，API 或图片下载服务返回错误状态码。")
    except Exception as e:
        logger.error(f"receipt_assistant: Process failed: {e}")
        await receipt_cmd.finish(f"小票识别翻译失败：{str(e)}")
