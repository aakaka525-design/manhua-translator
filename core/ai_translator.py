"""
AI Translator - 支持多个 AI 提供商进行翻译。

支持：
- PPIO (GLM, DeepSeek, Qwen 等)
- Gemini (Google OpenAI 兼容 API)
"""

import os
import asyncio
import logging
import time
from typing import Optional

from openai import OpenAI
from dotenv import load_dotenv

from .logging_config import setup_module_logger, get_log_level

load_dotenv()

# 配置日志
logger = setup_module_logger(
    __name__,
    "ai/ai_translator.log",
    level=get_log_level("AI_TRANSLATOR_LOG_LEVEL", logging.INFO),
)

# 启用 OpenAI SDK 详细日志（显示重试原因）
if os.getenv("DEBUG_OPENAI") == "1":
    logging.getLogger("openai").setLevel(logging.DEBUG)
    logging.getLogger("httpx").setLevel(logging.DEBUG)


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
    
    # 移除可能回显的结构化前缀（TEXT/CTX）
    text = re.sub(r'^\s*(TEXT|CTX)\s*[:：]\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\b(TEXT|CTX)\s*[:：]\s*', '', text, flags=re.IGNORECASE)
    
    # 移除 AI 可能添加的 "翻译:" 前缀
    text = re.sub(r'^\s*翻译\s*[:：]\s*', '', text)

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
        
        # 从环境变量或参数加载模型（默认使用 Gemini 3 Flash）
        self.model = model or os.getenv("PPIO_MODEL", "gemini-3-flash-preview")
        
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
        
        # 禁用 SDK 内部重试，让我们自己控制并记录错误原因
        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            max_retries=0,  # 禁用内部重试，便于查看真实错误
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
        
        prompt = f"""你是一位资深的漫画翻译专家。

# 任务
将以下文本翻译为{target_name}。

# 规则
1. 口语化自然翻译，适合漫画对白
2. 输入可能含 OCR 错误，请适当纠正（如 Im → I'm）
3. 专有名词（人名/地名）音译，不可直译
4. 若原文含多种语言，全部翻译为{target_name}，不保留原文
5. 只输出翻译结果，不要任何解释或注释

原文: {text}

翻译:"""
        
        start = time.perf_counter()
        logger.debug(f"translate: model={self.model} len={len(text)}")
        try:
            result = await self._call_api(prompt, max_tokens=500)
            duration_ms = (time.perf_counter() - start) * 1000
            logger.info(f"translate: ok model={self.model} ms={duration_ms:.0f} out_len={len(result)}")
            return result
        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.error(f"translate: error model={self.model} ms={duration_ms:.0f} err={type(e).__name__}: {e}")
            return f"[翻译失败] {text}"
    
    async def _call_api(self, prompt: str, max_tokens: int = 500) -> str:
        """统一的 API 调用方法。"""
        loop = asyncio.get_event_loop()
        
        if self.is_gemini:
            from google.genai import types
            def call_gemini():
                try:
                    response = self.client.models.generate_content(
                        model=self.model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            max_output_tokens=max_tokens,
                            temperature=0.3,  # Lower temp for faster, more consistent output
                        )
                    )
                    return response.text
                except Exception as e:
                    logger.error(f"Gemini API error: {type(e).__name__}: {e}")
                    raise

            return await loop.run_in_executor(None, call_gemini)
        else:
            # PPIO / OpenAI 兼容调用
            def call_openai():
                try:
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=max_tokens,
                        stream=False,
                    )
                    return response.choices[0].message.content.strip()
                except Exception as e:
                    # 记录详细错误信息
                    error_msg = f"{type(e).__name__}: {e}"
                    if hasattr(e, 'status_code'):
                        error_msg = f"HTTP {e.status_code}: {error_msg}"
                    if hasattr(e, 'response') and e.response:
                        try:
                            error_msg += f" | Response: {e.response.text[:200]}"
                        except:
                            pass
                    logger.error(f"OpenAI API error: {error_msg}")
                    raise
            
            return await loop.run_in_executor(None, call_openai)
    
    async def translate_batch(
        self,
        texts: list[str],
        output_format: str = "numbered",
        contexts: Optional[list[str]] = None,
    ) -> list[str]:
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

        def _strip_code_fence(text: str) -> str:
            t = (text or "").strip()
            if t.startswith("```"):
                lines = t.splitlines()
                if lines and lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                return "\n".join(lines).strip()
            return t

        def _extract_json_objects(text: str) -> list[str]:
            objects = []
            depth = 0
            start = None
            in_str = False
            escape = False
            for i, ch in enumerate(text):
                if in_str:
                    if escape:
                        escape = False
                    elif ch == "\\":
                        escape = True
                    elif ch == "\"":
                        in_str = False
                    continue
                if ch == "\"":
                    in_str = True
                    continue
                if ch == "{":
                    if depth == 0:
                        start = i
                    depth += 1
                elif ch == "}" and depth > 0:
                    depth -= 1
                    if depth == 0 and start is not None:
                        objects.append(text[start : i + 1])
                        start = None
            return objects

        def _parse_numbered_lines(text: str, expected_count: int | None = None):
            lines = text.split("\n")
            translations = []
            numbered: dict[int, str] = {}
            unnumbered: list[str] = []
            has_numbered = False
            for line in lines:
                line = line.strip()
                if line:
                    import re
                    match = re.match(r"^(\d+)\s*[\.\)\）:\-、：]\s*(.+)$", line)
                    if match:
                        idx = int(match.group(1))
                        if idx not in numbered:
                            numbered[idx] = match.group(2).strip()
                        has_numbered = True
                    else:
                        unnumbered.append(line)
            if not has_numbered:
                return unnumbered, False

            max_idx = max(numbered) if numbered else 0
            if expected_count and max_idx < expected_count:
                max_idx = expected_count
            # Don't use fallback for missing numbers - mark as empty to trigger failure handler
            for i in range(1, max_idx + 1):
                if i in numbered:
                    translations.append(numbered[i])
                else:
                    # Missing number - return empty string, will be marked as failed later
                    translations.append("")
                    logger.warning(f"AI response missing number {i}, marking as failed")
            if expected_count:
                translations = translations[:expected_count]
                while len(translations) < expected_count:
                    translations.append("")
            return translations, True
        
        cleaned_texts = [clean_text(t) for t in texts]
        if contexts is None:
            cleaned_contexts = ["" for _ in texts]
        else:
            cleaned_contexts = [clean_text(t) if t else "" for t in contexts]
            if len(cleaned_contexts) < len(texts):
                cleaned_contexts += [""] * (len(texts) - len(cleaned_contexts))
            elif len(cleaned_contexts) > len(texts):
                cleaned_contexts = cleaned_contexts[: len(texts)]
        valid_pairs = [(i, t) for i, t in enumerate(cleaned_texts) if t.strip()]
        
        if not valid_pairs:
            return ["" for _ in texts]
        
        target_name = self._get_lang_name(self.target_lang)
        def _read_env_int(name: str, default: int) -> int:
            raw = os.getenv(name)
            if not raw:
                return default
            try:
                value = int(raw)
            except ValueError:
                return default
            return value if value > 0 else default

        def _format_entry(index: int, text: str, ctx: str) -> str:
            if ctx:
                return f"{index}. TEXT: {text}\n   CTX: {ctx}"
            return f"{index}. {text}"
        
        output_hint = "请用数字编号格式输出翻译结果。禁止添加任何注释、说明或括号备注。"
        if output_format == "json":
            output_hint = (
                "请用数字编号格式输出翻译结果，每一条必须是单行 JSON："
                '{"top":"...","bottom":"..."}。不要输出数组、代码块或多行 JSON。'
                "禁止添加任何注释、说明或括号备注。"
            )
        max_retries = 2

        async def _translate_pairs(
            pairs: list[tuple[int, str]],
            slice_idx: int | None = None,
            slice_total: int | None = None,
        ) -> list[tuple[int, str]]:
            numbered_texts = "\n".join(
                _format_entry(i + 1, t, cleaned_contexts[orig_idx])
                for i, (orig_idx, t) in enumerate(pairs)
            )
            prompt = f"""# Role
你是一位资深的**漫画/汉化组翻译专家**，精通多国语言与{target_name}的文化转换。

# OCR 纠错
输入可能含OCR识别错误。你会看到每条文本的可选上下文(CTX)，来自同页相邻 1-2 个气泡。
请结合上下文纠正拼写/字符错误；允许多字符纠错，但只有在把握足够时才修改，不确定则保留原文。
例如：이닌 억은 → 이번 역은
若为英文，纠正常见拼写错误（如 DONT → DON'T, Im → I'm, OLAINKEI → BLANKET）。

# 专有名词（必须音译，禁止保留原文）
韩文人名必须音译为中文，绝不可保留韩文原文！
例如：이수희 → 李秀熙, 김민수 → 金民秀, 박지현 → 朴智贤
地名/站名同理：사당 → 舍堂, 강남 → 江南, 東京 → 东京

# 多语言处理（禁止保留原文）
若原文含韩文/日文/英文，必须全部翻译为{target_name}，绝不可返回原文！
特别注意：人名喊叫（如"이수희!!"）必须翻译为"李秀熙!!"

# 核心原则
**语境优先，拒绝字面翻译**：理解原文意图后，用中文母语者的方式自然表达。
韩语词汇可能有多义，必须选择符合语境的译法：
- 실물（描述人）→ 真人，不是"实物"
- 大丈夫（日语）→ 没问题，不是"大丈夫"
- 先輩（日语）→ 前辈/学长，根据语境选择

# 翻译规则
1. **情感还原**：保留原文的情感强度，兴奋/愤怒/害羞等情绪要传神
2. **口语自然**：漫画对白要像真人说话，可用网络用语/俚语
3. **俚语对应**：韩语俚语转中文俚语（미친→卧槽, 개→巨/超, 대박→牛逼）
4. **简练有力**：考虑气泡大小，但不牺牲情感
5. **拟声词**：转换为{target_name}习惯表达
6. **语气推断**：根据说话人特征调整用词

# 待翻译文本
{numbered_texts}

{output_hint}"""

            slice_note = ""
            if slice_idx is not None and slice_total:
                slice_note = f" slice={slice_idx + 1}/{slice_total}"
            logger.info(
                f"batch: model={self.model} count={len(pairs)} total_len={len(numbered_texts)}{slice_note}"
            )
            for attempt in range(max_retries + 1):
                try:
                    start = time.perf_counter()
                    result = await self._call_api(prompt, max_tokens=2000)
                    duration_ms = (time.perf_counter() - start) * 1000

                    # 解析结果
                    translations = []
                    has_numbered = False
                    if output_format == "json":
                        json_text = _strip_code_fence(result)
                        translations = _extract_json_objects(json_text)
                        if not translations:
                            translations, has_numbered = _parse_numbered_lines(
                                result, expected_count=len(pairs)
                            )
                    else:
                        translations, has_numbered = _parse_numbered_lines(
                            result, expected_count=len(pairs)
                        )

                    if not has_numbered:
                        # Fallback: split single-line output by common separators
                        if len(translations) == 1 and len(pairs) > 1:
                            import re
                            parts = re.split(r"\s*(?:/|\||｜|;|；)\s*", translations[0])
                            parts = [p for p in parts if p]
                            if len(parts) == len(pairs):
                                translations = parts

                    slice_results: list[tuple[int, str]] = []
                    import re as _re
                    _hangul_check = _re.compile(r'[\uac00-\ud7a3]')
                    for (orig_idx, orig_text), trans in zip(pairs, translations):
                        cleaned = _clean_ai_annotations(trans)
                        # Empty translation means AI skipped this number
                        if not cleaned.strip():
                            slice_results.append((orig_idx, f"[翻译失败] {orig_text}"))
                        # Detect Korean text returned unchanged (AI failed to translate names)
                        elif _hangul_check.search(cleaned) and cleaned.strip() == orig_text.strip():
                            logger.warning(f"AI returned Korean unchanged: {orig_text}")
                            slice_results.append((orig_idx, f"[翻译失败] {orig_text}"))
                        else:
                            slice_results.append((orig_idx, cleaned))
                    if len(translations) < len(pairs):
                        for i in range(len(translations), len(pairs)):
                            orig_idx, orig_text = pairs[i]
                            slice_results.append((orig_idx, f"[翻译失败] {orig_text}"))

                    logger.info(
                        f"batch: ok model={self.model} ms={duration_ms:.0f} out_count={len(slice_results)}{slice_note}"
                    )
                    return slice_results

                except Exception as e:
                    if attempt < max_retries:
                        error_msg = str(e)
                        # 如果是 400 错误，打印更多诊断信息
                        if '400' in error_msg:
                            logger.warning(
                                f"batch: retry {attempt + 1}/{max_retries} err={e} count={len(pairs)} len={len(numbered_texts)}{slice_note}"
                            )
                        else:
                            logger.warning(
                                f"batch: retry {attempt + 1}/{max_retries} err={e}{slice_note}"
                            )
                        await asyncio.sleep(1)
                    else:
                        logger.error(
                            f"batch: error model={self.model} err={e} count={len(pairs)} len={len(numbered_texts)}{slice_note}"
                        )
                        return [
                            (orig_idx, f"[翻译失败] {orig_text}")
                            for orig_idx, orig_text in pairs
                        ]

            return [
                (orig_idx, f"[翻译失败] {orig_text}")
                for orig_idx, orig_text in pairs
            ]

        chunk_size = _read_env_int("AI_TRANSLATE_BATCH_CHUNK_SIZE", 20)  # Larger batches = fewer API calls
        concurrency = _read_env_int("AI_TRANSLATE_BATCH_CONCURRENCY", 2)  # Reduced to avoid rate limits

        if len(valid_pairs) <= chunk_size:
            slice_results = await _translate_pairs(valid_pairs)
            full_results = ["" for _ in texts]
            for orig_idx, trans in slice_results:
                full_results[orig_idx] = trans
            return full_results

        slices = [
            valid_pairs[i : i + chunk_size]
            for i in range(0, len(valid_pairs), chunk_size)
        ]
        sem = asyncio.Semaphore(concurrency)

        async def _run_slice(idx: int, pairs: list[tuple[int, str]]):
            async with sem:
                return await _translate_pairs(pairs, idx, len(slices))

        results = await asyncio.gather(
            *[_run_slice(i, pairs) for i, pairs in enumerate(slices)]
        )
        full_results = ["" for _ in texts]
        for slice_results in results:
            for orig_idx, trans in slice_results:
                full_results[orig_idx] = trans
        return full_results


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
