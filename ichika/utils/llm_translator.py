import re
import httpx
from nonebot import logger
from ichika.config import get as cfg_get

def is_chinese_text(text: str) -> bool:
    """初步判定文本是否为中文或无需翻译的符号。
    如果不含日韩文等明显外文特征，且包含汉字或完全无特定语言字符，则跳过翻译。
    """
    if not text.strip():
        return True
        
    # 如果含有日文假名，视为外文
    if re.search(r'[\u3040-\u309F\u30A0-\u30FF]', text):
        return False
    
    # 如果含有韩文，视为外文
    if re.search(r'[\uac00-\ud7a3]', text):
        return False
        
    cjk_matches = re.findall(r'[\u4e00-\u9fff]', text)
    letters_matches = re.findall(r'[a-zA-Z]', text)
    
    # 如果完全没有汉字且有英文字母，可能是纯英文，需要翻译
    if len(letters_matches) > 0 and len(cjk_matches) == 0:
        return False
        
    # 如果含有汉字且没有假名，大概率为中文推文
    if len(cjk_matches) > 0:
        return True
        
    # 只有符号、表情或数字的场合，不需要翻译
    return True


async def translate_tweet_text(text: str) -> str:
    """使用 LLM 翻译推文，发生异常或条件不满足时返回空字符串"""
    if not text.strip():
        return ""
        
    # 如果前端探测认为是中文，就不消耗API了
    if is_chinese_text(text):
        return ""
        
    api_key = cfg_get("twitter.llm_api_key")
    if not api_key:
        return ""
    
    api_url = cfg_get("twitter.llm_api_url") or "https://api.siliconflow.cn/v1/chat/completions"
    model = cfg_get("twitter.llm_model") or "Qwen/Qwen2.5-7B-Instruct"

    prompt = (
        "你是一个精通日语和中文二次元网络用语的同传翻译，请将以下推文翻译成自然流畅的中文，"
        "保留原本的语气和颜文字，不要带有翻译腔。如果本身就是纯中文或者无意义的英文字母则直接返回原文本。\n"
        "请直接输出翻译结果，不要带有任何多余的解释说明。"
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": text}
        ],
        "temperature": 0.3,
        "max_tokens": 512
    }
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(api_url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.warning(f"twitter_llm: LLM translation failed: {e}")
        return ""
