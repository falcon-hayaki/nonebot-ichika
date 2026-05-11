from nonebot import on_keyword, require
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, MessageSegment, Message
from nonebot.log import logger
from nonebot.exception import FinishedException
import httpx
import base64

from ichika.config import get as cfg_get

# 注册命令，使用关键词匹配以防 QQ 客户端将图片排在前面导致开头的正则匹配失败
receipt_cmd = on_keyword({"一花小票"}, priority=5, block=True)

PROMPT_TEXT = (
    "这是一张购物小票。请仔细、逐行识别出小票上的【所有】商品内容，绝不能遗漏任何一项，将商品名称翻译为中文，并以此格式输出：\n"
    "商品名(原文) - 商品名(中文翻译) - 价格\n"
    "如果有额外的折扣或税费也请列出。\n"
    "最后请统计出总金额。\n"
    "请确保内容完整，不要因为小票太长而截断或省略。直接输出整理好的账单结果，不需要任何额外的闲聊或解释。"
)

@receipt_cmd.handle()
async def _(bot: Bot, event: MessageEvent, state):
    img_urls = []
    
    if event.reply:
        for seg in event.reply.message:
            if seg.type == "image" and seg.data.get("url"):
                img_urls.append(seg.data.get("url"))

    for seg in event.message:
        if seg.type == "image" and seg.data.get("url"):
            img_urls.append(seg.data.get("url"))
            
    if not img_urls:
        await receipt_cmd.finish("请发送带有小票图片的指令（如发文本「一花小票」附加上图片，或者对小票图片回复「一花小票」）")

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
        base_url = cfg_get("gemini_api_base") or "https://generativelanguage.googleapis.com"
        model_name = cfg_get("gemini_receipt_model") or "gemini-2.5-Flash"
        gemini_url = f"{base_url}/v1beta/models/{model_name}:generateContent?key={api_key}"
        
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
                "maxOutputTokens": 4096,
            }
        }

        gemini_proxy = cfg_get("gemini_proxy") or cfg_get("proxy")
        if not gemini_proxy:
            gemini_proxy = None
        async with httpx.AsyncClient(timeout=60.0, proxy=gemini_proxy) as client:
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

    except FinishedException:
        # Nonebot 用于中断执行流的特殊异常，不要被误杀拦截
        raise
    except httpx.HTTPStatusError as e:
        err_msg = e.response.text
        try:
            err_json = e.response.json()
            if "error" in err_json and "message" in err_json["error"]:
                err_msg = err_json["error"]["message"]
        except Exception:
            pass
        logger.error(f"receipt_assistant: HTTP Error {e.response.status_code}: {e.response.text}")
        await receipt_cmd.finish(f"小票识别翻译失败 (HTTP {e.response.status_code})：{err_msg}")
    except Exception as e:
        logger.error(f"receipt_assistant: Process failed: {e}")
        await receipt_cmd.finish(f"小票识别翻译失败：{str(e)}")
