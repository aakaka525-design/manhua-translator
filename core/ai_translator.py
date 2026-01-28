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


def _clean_ai_annotations(text: str) -> str:
    """
    清理翻译结果中可能残留的 AI 注释。
    
    过滤模式:
    - (Note: ...) 或 (注: ...)
    - "This means..." 或 "这意味着..."
    - Without more context, ...
    - This seems to be...
    """
    import re
    
    if not text:
        return text
    
    # 移除括号内的注释 (Note: ...), (注: ...), etc.
    # 支持闭合和未闭合的括号
    text = re.sub(r'\s*\(Note:.*?(\)|$)', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\s*\(注[:：].*?(\)|$)', '', text, flags=re.DOTALL)
    text = re.sub(r'\s*\(This\s+(seems?|means?|appears?).*?(\)|$)', '', text, flags=re.IGNORECASE | re.DOTALL)
    
    # 移除独立的解释性句子
    text = re.sub(r'Without\s+more\s+context[,，].*?([。.]|$)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'This\s+(seems?|means?|appears?)\s+to\s+be.*?([。.]|$)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'direct\s+translation\s+might\s+not.*?([。.]|$)', '', text, flags=re.IGNORECASE)
    
    return text.strip()

class AITranslator:
    """支持多个 AI 提供商的翻译器。"""
    
    # Gemini 模型列表 (2026-01 更新：Gemini 2.0 将于 2026年3月31日弃用)
    GEMINI_MODELS = {
        # Gemini 3.x 系列
        'gemini-3-pro-preview', 'gemini-3-flash-preview',
        # Gemini 2.5 系列
        'gemini-2.5-flash', 'gemini-2.5-flash-lite', 'gemini-2.5-pro-exp',
    }
    

    
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
        
        # 模型名称兼容性映射
        _compat_map = {
            'gemini-3-flash': 'gemini-3-flash-preview',
            'gemini-3-pro': 'gemini-3-pro-preview',
        }
        if self.model in _compat_map:
            logger.warning(f"自动将模型 {self.model} 映射为 {_compat_map[self.model]}")
            self.model = _compat_map[self.model]

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
        """初始化 Gemini 客户端（使用原生 google-genai SDK）。"""
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise ImportError("请安装 google-genai 包: pip install google-genai")

        self.api_key = os.getenv("GEMINI_API_KEY")
        
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")
        
        # 使用 v1alpha 版本以支持最新的 preview 模型
        self.client = genai.Client(
            api_key=self.api_key,
            http_options={'api_version': 'v1alpha'}
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
        """统一的 API 调用方法。"""
        loop = asyncio.get_event_loop()
        
        if self.is_gemini:
            from google.genai import types
            def call_gemini():
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        max_output_tokens=max_tokens,
                        temperature=0.7,
                    )
                )
                return response.text

            return await loop.run_in_executor(None, call_gemini)
        else:
            # PPIO / OpenAI 兼容调用
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
        
        prompt = f"""# Role
你是一位资深的**漫画/汉化组翻译专家**，精通多国语言与{target_name}的文化转换。

# OCR 纠错
输入可能含OCR识别错误，请根据上下文自动纠正拼写/字符错误。
例如：이닌 억은 → 이번 역은

# 专有名词（必须音译）
地名、人名、站名等专有名词必须音译，不可直译。
例如：사당 → 舍堂, 東京 → 东京, 강남 → 江南

# 翻译规则
1. **语境优先**：对话用口语，旁白用书面语
2. **简练有力**：考虑气泡大小
3. **拟声词**：转换为{target_name}习惯表达
4. **语气推断**：根据说话人特征调整用词

# 输出格式
{numbered_texts}

请用数字编号格式输出翻译结果。禁止添加任何注释、说明或括号备注。"""
        
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
                
                # 重建完整结果，并清理 AI 注释
                full_results = ["" for _ in texts]
                for (orig_idx, _), trans in zip(valid_pairs, translations):
                    full_results[orig_idx] = _clean_ai_annotations(trans)
                
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
