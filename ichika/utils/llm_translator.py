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


def is_garbled_output(text: str) -> bool:
    """检测 LLM 输出是否为乱码/循环输出。"""
    if not text:
        return False

    # 检测重复 token 模式（如 "DD DD DD" 或 "https https https"）
    words = text.split()
    if len(words) >= 10:
        # 取前10个词，如果超过一半相同则认为是循环
        most_common = max(set(words[:20]), key=words[:20].count)
        count = words[:20].count(most_common)
        if count >= 8:
            return True

    # 检测单个字符大量重复（如 "DDDDDDDD"）
    if re.search(r'(.)\1{15,}', text):
        return True

    # 检测 url 片段大量重复（如 "https https https"）
    if text.count('https') > 10 or text.count('DD') > 10:
        return True

    return False


def preprocess_tweet(text: str) -> str:
    """翻译前预处理推文，去除 t.co 链接等干扰内容。"""
    # 去除 Twitter 短链接（t.co/xxxxx）
    text = re.sub(r'https://t\.co/\S+', '', text)
    # 去除多余空行
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


async def translate_tweet_text(text: str) -> str:
    """使用 Gemini LLM 翻译推文，发生异常或条件不满足时返回空字符串"""
    if not text.strip():
        return ""
        
    # 如果前端探测认为是中文，就不消耗API了
    if is_chinese_text(text):
        return ""

    # 预处理，去除链接等干扰
    clean_text = preprocess_tweet(text)
    if not clean_text:
        return ""

    api_key = cfg_get("twitter.llm_api_key")
    if not api_key:
        return ""

    # Gemini OpenAI 兼容接口
    # 也支持用 twitter.llm_api_url 自定义（如反代或其他服务）
    api_url = (
        cfg_get("twitter.llm_api_url")
        or "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    )
    model = cfg_get("twitter.llm_model") or "gemini-3.1-flash-lite"

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
            {"role": "user", "content": clean_text}
        ],
        "temperature": 0.3,
        "max_completion_tokens": 512
    }
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(api_url, json=payload, headers=headers)
            if not resp.is_success:
                logger.warning(f"twitter_llm: HTTP {resp.status_code} - {resp.text}")
                resp.raise_for_status()
            data = resp.json()
            result = data["choices"][0]["message"]["content"].strip()

            # 乱码检测：如果输出异常则丢弃
            if is_garbled_output(result):
                logger.warning(f"twitter_llm: 检测到乱码输出，已丢弃。原文: {clean_text[:50]}...")
                return ""

            return result
    except Exception as e:
        logger.warning(f"twitter_llm: LLM translation failed: {e}")
        return ""
