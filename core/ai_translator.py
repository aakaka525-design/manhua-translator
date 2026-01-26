"""
AI Translator - 支持多个 AI 提供商进行翻译。

支持：
- PPIO (GLM, DeepSeek, Qwen 等)
- Gemini (Google OpenAI 兼容 API)
"""

import os
import asyncio
import logging
from typing import Optional

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# 配置日志
logger = logging.getLogger(__name__)


class AITranslator:
    """支持多个 AI 提供商的翻译器。"""
    
    # Gemini 模型列表
    GEMINI_MODELS = {'gemini-2.0-flash', 'gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-2.0-flash-exp'}
    
    # Gemini OpenAI 兼容 API 地址
    GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
    
    def __init__(
        self,
        source_lang: str = "en",
        target_lang: str = "zh-CN",
        model: Optional[str] = None,
    ):
        self.source_lang = source_lang
        self.target_lang = target_lang
        
        # 从环境变量或参数加载模型
        self.model = model or os.getenv("PPIO_MODEL", "glm-4-flash-250414")
        
        # 检查是否是 Gemini 模型
        self.is_gemini = any(g in self.model for g in self.GEMINI_MODELS)
        
        logger.info(f"初始化翻译器: model={self.model}, is_gemini={self.is_gemini}")
        
        if self.is_gemini:
            self._init_gemini()
        else:
            self._init_ppio()
        
        # 语言映射
        self._lang_names = {
            "en": "English",
            "zh-CN": "Simplified Chinese",
            "zh": "Simplified Chinese",
            "zh-TW": "Traditional Chinese",
            "ja": "Japanese",
            "ko": "Korean",
            "korean": "Korean",
        }
    
    def _init_ppio(self):
        """初始化 PPIO (OpenAI 兼容) 客户端。"""
        self.api_key = os.getenv("PPIO_API_KEY")
        self.base_url = os.getenv("PPIO_BASE_URL", "https://api.ppio.com/openai")
        
        if not self.api_key:
            raise ValueError("PPIO_API_KEY not found in environment variables")
        
        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
        )
    
    def _init_gemini(self):
        """初始化 Gemini 客户端（使用 OpenAI 兼容 API）。"""
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.base_url = os.getenv("GEMINI_BASE_URL", self.GEMINI_BASE_URL)
        
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")
        
        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
        )
    
    def _get_lang_name(self, code: str) -> str:
        return self._lang_names.get(code, code)
    
    async def translate(self, text: str) -> str:
        """翻译单个文本。"""
        if not text or not text.strip():
            return text
        
        target_name = self._get_lang_name(self.target_lang)
        
        prompt = f"""You are a professional translator for manga/comics.
Translate the following text to {target_name}.
This is dialogue from a comic, translate it naturally.
You MUST translate, do NOT return the original text.
Only output the translation, nothing else.

Text: {text}

{target_name} Translation:"""
        
        try:
            return await self._call_api(prompt, max_tokens=500)
        except Exception as e:
            print(f"AI Translation error: {e}")
            return f"[翻译失败] {text}"
    
    async def _call_api(self, prompt: str, max_tokens: int = 500) -> str:
        """统一的 API 调用方法（PPIO 和 Gemini 都使用 OpenAI 兼容接口）。"""
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                stream=False,
            )
        )
        return response.choices[0].message.content.strip()
    
    async def translate_batch(self, texts: list[str]) -> list[str]:
        """批量翻译多个文本。"""
        if not texts:
            return []
        
        # 预处理文本
        def clean_text(t: str) -> str:
            if not t:
                return ""
            import re
            cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', t)
            return cleaned[:500] if len(cleaned) > 500 else cleaned
        
        cleaned_texts = [clean_text(t) for t in texts]
        valid_pairs = [(i, t) for i, t in enumerate(cleaned_texts) if t.strip()]
        
        if not valid_pairs:
            return ["" for _ in texts]
        
        target_name = self._get_lang_name(self.target_lang)
        numbered_texts = "\n".join(f"{i+1}. {t}" for i, (_, t) in enumerate(valid_pairs))
        
        prompt = f"""You are a professional translator for manga/comics.
Translate ALL the following texts to {target_name}.
These are dialogues from a comic, translate them naturally.
You MUST translate every line, do NOT return any original text.
Output each translation on a new line with the same number prefix (1. 2. 3. etc).
Only output the translations, nothing else.

{numbered_texts}"""
        
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                result = await self._call_api(prompt, max_tokens=2000)
                
                # 解析结果
                lines = result.split("\n")
                translations = []
                for line in lines:
                    line = line.strip()
                    if line:
                        import re
                        match = re.match(r"^\d+\.\s*(.+)$", line)
                        if match:
                            translations.append(match.group(1))
                        else:
                            translations.append(line)
                
                # 重建完整结果
                full_results = ["" for _ in texts]
                for (orig_idx, _), trans in zip(valid_pairs, translations):
                    full_results[orig_idx] = trans
                
                for i, (orig_idx, orig_text) in enumerate(valid_pairs):
                    if i >= len(translations):
                        full_results[orig_idx] = f"[翻译失败] {orig_text}"
                
                return full_results
                
            except Exception as e:
                if attempt < max_retries:
                    error_msg = str(e)
                    # 如果是 400 错误，打印更多诊断信息
                    if '400' in error_msg:
                        print(f"AI Translation retry {attempt + 1}/{max_retries}: {e}")
                        print(f"  文本数量: {len(valid_pairs)}, 总长度: {len(numbered_texts)}")
                    else:
                        print(f"AI Translation retry {attempt + 1}/{max_retries}: {e}")
                    await asyncio.sleep(1)
                else:
                    print(f"AI Batch Translation error: {e}")
                    print(f"  失败的请求: {len(valid_pairs)} 条文本, 总长度 {len(numbered_texts)} 字符")
                    return [f"[翻译失败] {t}" if t else "" for t in texts]
        
        return [f"[翻译失败] {t}" if t else "" for t in texts]


# 测试
if __name__ == "__main__":
    async def test():
        translator = AITranslator()
        
        # 单个翻译
        result = await translator.translate("Hello, how are you?")
        print(f"Single: {result}")
        
        # 批量翻译
        texts = ["Hello", "How are you?", "See you later!"]
        results = await translator.translate_batch(texts)
        print(f"Batch: {results}")
    
    asyncio.run(test())
