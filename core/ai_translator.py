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
import hashlib
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

_FAILURE_MARKER = "[翻译失败]"

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


def _format_log_text(text: str, mode: str, limit: int) -> str | None:
    if text is None:
        return ""
    mode = (mode or "off").strip().lower()
    if mode == "off":
        return None
    raw = str(text)
    if mode == "full":
        return raw
    if mode == "hash":
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return f"sha256:{digest} len={len(raw)}"
    if mode == "snippet":
        if limit <= 0:
            return ""
        if len(raw) <= limit * 2:
            return raw
        return f"{raw[:limit]}...{raw[-limit:]}"
    return None


def _read_env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


_GLOBAL_API_SEMAPHORE: asyncio.Semaphore | None = None
_GLOBAL_API_SEMAPHORE_LIMIT: int | None = None


def _get_global_api_semaphore() -> asyncio.Semaphore | None:
    """
    Optional cross-task backpressure for AI calls.

    This is intentionally disabled by default to preserve existing behavior.
    When enabled, it caps concurrent primary+fallback requests across the process,
    which helps reduce provider overload (503/timeout) under multi-chapter load.
    """
    global _GLOBAL_API_SEMAPHORE, _GLOBAL_API_SEMAPHORE_LIMIT

    limit = _read_env_int("AI_TRANSLATE_MAX_INFLIGHT_CALLS", 0)
    if limit <= 0:
        _GLOBAL_API_SEMAPHORE = None
        _GLOBAL_API_SEMAPHORE_LIMIT = None
        return None

    if _GLOBAL_API_SEMAPHORE is None or _GLOBAL_API_SEMAPHORE_LIMIT != limit:
        _GLOBAL_API_SEMAPHORE = asyncio.Semaphore(limit)
        _GLOBAL_API_SEMAPHORE_LIMIT = limit
    return _GLOBAL_API_SEMAPHORE


def _get_log_config():
    mode = (os.getenv("AI_TRANSLATOR_LOG_MODE") or "off").strip().lower()
    limit = _read_env_int("AI_TRANSLATOR_LOG_SNIPPET_CHARS", 120)
    log_ctx = os.getenv("AI_TRANSLATOR_LOG_CTX", "0") == "1"
    return mode, limit, log_ctx


def _sanitize_log_text(text: str) -> str:
    return (text or "").replace("\n", "\\n")


def _estimate_batch_max_tokens(item_count: int, total_chars: int) -> int:
    """
    Estimate max output tokens for batch translation.

    Keeps a conservative upper bound to reduce long-tail latency caused by
    overly large max_tokens while preserving enough headroom for multi-item output.
    """
    hard_cap = _read_env_int("AI_TRANSLATE_BATCH_MAX_TOKENS", 4000)
    base = _read_env_int("AI_TRANSLATE_BATCH_MAX_TOKENS_BASE", 320)
    per_item = _read_env_int("AI_TRANSLATE_BATCH_MAX_TOKENS_PER_ITEM", 120)
    per_chars = _read_env_int("AI_TRANSLATE_BATCH_MAX_TOKENS_PER_200_CHARS", 40)
    min_tokens = _read_env_int("AI_TRANSLATE_BATCH_MAX_TOKENS_MIN", 320)

    item_count = max(1, int(item_count or 0))
    total_chars = max(0, int(total_chars or 0))

    estimated = base + per_item * item_count + (total_chars // 200) * per_chars
    return max(min_tokens, min(hard_cap, estimated))

class AITranslator:
    """支持多个 AI 提供商的翻译器。"""
    
    # Gemini 模型列表
    GEMINI_MODELS = {
        # Gemini 3.x 系列 (推荐)
        'gemini-3-pro-preview', 'gemini-3-flash-preview',
        # Gemini 2.5 系列
        'gemini-2.5-flash', 'gemini-2.5-flash-lite', 'gemini-2.5-pro-exp',
    }
    

    
    def __init__(
        self,
        source_lang: str = "en",
        target_lang: str = "zh-CN",
        model: Optional[str] = None,
        provider: Optional[str] = None,
        allow_gemini_model_fallback: bool = True,
    ):
        self.source_lang = source_lang
        self.target_lang = target_lang
        
        provider = (provider or os.getenv("AI_PROVIDER") or "").strip().lower()
        if provider and provider not in ("gemini", "ppio"):
            raise ValueError("AI_PROVIDER must be 'gemini' or 'ppio'")

        ppio_key = os.getenv("PPIO_API_KEY")
        gemini_key = os.getenv("GEMINI_API_KEY")
        if not provider:
            if ppio_key and gemini_key:
                raise ValueError(
                    "AI_PROVIDER must be set when both PPIO_API_KEY and GEMINI_API_KEY are present"
                )
            provider = "gemini" if gemini_key else "ppio"
        self.provider = provider

        if provider == "gemini":
            # 从环境变量或参数加载模型（默认使用 Gemini 3 Flash）
            self.model = model or os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
            # 模型名称兼容性映射
            _compat_map = {
                'gemini-3-flash': 'gemini-3-flash-preview',
                'gemini-3-pro': 'gemini-3-pro-preview',
            }
            if self.model in _compat_map:
                logger.warning(f"自动将模型 {self.model} 映射为 {_compat_map[self.model]}")
                self.model = _compat_map[self.model]
            self.is_gemini = True
        else:
            # PPIO 模型
            self.model = model or os.getenv("PPIO_MODEL", "zai-org/glm-4.7-flash")
            self.is_gemini = False
        self._allow_gemini_model_fallback = allow_gemini_model_fallback
        self._fallback_translator: Optional["AITranslator"] = None
        self._gemini_model_fallback_translators: dict[str, "AITranslator"] = {}
        self.last_metrics: Optional[dict] = None
        
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

    def _gemini_fallback_model_names(self) -> list[str]:
        if not self.is_gemini or not self._allow_gemini_model_fallback:
            return []
        raw = (os.getenv("AI_TRANSLATE_GEMINI_FALLBACK_MODELS") or "").strip()
        if raw:
            if raw.lower() in {"off", "none", "disable", "disabled"}:
                return []
            candidates = [m.strip() for m in raw.split(",") if m.strip()]
        else:
            candidates = ["gemini-2.5-flash", "gemini-2.5-flash-lite"]
        ordered: list[str] = []
        for model_name in candidates:
            if model_name == self.model:
                continue
            if model_name not in ordered:
                ordered.append(model_name)
        return ordered

    def _fallback_provider(self) -> Optional[str]:
        provider = (os.getenv("AI_TRANSLATE_FALLBACK_PROVIDER") or "").strip().lower()
        if not provider:
            if self.provider == "gemini" and os.getenv("PPIO_API_KEY"):
                return "ppio"
            return None
        if provider not in {"gemini", "ppio"}:
            return None
        if provider == self.provider:
            return None
        return provider

    @staticmethod
    def _is_overload_error(exc: Exception) -> bool:
        msg = str(exc).lower()
        return (
            "503" in msg
            or "unavailable" in msg
            or "overload" in msg
            or "overloaded" in msg
            or "timeout" in msg
            or "timed out" in msg
            or "empty response" in msg
        )

    def _get_fallback_translator(self) -> Optional["AITranslator"]:
        provider = self._fallback_provider()
        if provider is None:
            return None
        if provider == "ppio" and not os.getenv("PPIO_API_KEY"):
            return None
        if provider == "gemini" and not os.getenv("GEMINI_API_KEY"):
            return None
        if self._fallback_translator is None:
            fallback_model = (
                os.getenv("PPIO_MODEL", "zai-org/glm-4.7-flash")
                if provider == "ppio"
                else os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
            )
            self._fallback_translator = AITranslator(
                source_lang=self.source_lang,
                target_lang=self.target_lang,
                model=fallback_model,
                provider=provider,
            )
        return self._fallback_translator

    def _get_gemini_model_fallback_translators(self) -> list["AITranslator"]:
        translators: list["AITranslator"] = []
        if not os.getenv("GEMINI_API_KEY"):
            return translators
        for model_name in self._gemini_fallback_model_names():
            if model_name not in self._gemini_model_fallback_translators:
                self._gemini_model_fallback_translators[model_name] = AITranslator(
                    source_lang=self.source_lang,
                    target_lang=self.target_lang,
                    model=model_name,
                    provider="gemini",
                    allow_gemini_model_fallback=False,
                )
            translators.append(self._gemini_model_fallback_translators[model_name])
        return translators

    def _fallback_translator_chain(self) -> list["AITranslator"]:
        chain = self._get_gemini_model_fallback_translators()
        provider_fallback = self._get_fallback_translator()
        if provider_fallback is not None:
            chain.append(provider_fallback)
        return chain

    async def _call_api_with_timeout(self, prompt: str, max_tokens: int) -> str:
        """
        Call primary provider with optional timeout guard.

        Timeout guard is only enabled when fallback translator is available,
        so single-provider setups keep previous behavior.
        """
        timeout_ms = _read_env_int("AI_TRANSLATE_PRIMARY_TIMEOUT_MS", 12000)
        has_fallback = bool(self._fallback_translator_chain())

        async def _do_call() -> str:
            if timeout_ms <= 0 or not has_fallback:
                return await self._call_api(prompt, max_tokens=max_tokens)
            try:
                return await asyncio.wait_for(
                    self._call_api(prompt, max_tokens=max_tokens),
                    timeout=timeout_ms / 1000.0,
                )
            except asyncio.TimeoutError as exc:
                raise RuntimeError(f"primary timeout after {timeout_ms}ms") from exc

        sem = _get_global_api_semaphore()
        if sem is None:
            return await _do_call()

        async with sem:
            return await _do_call()
    
    async def translate(self, text: str) -> str:
        """翻译单个文本。"""
        if not text or not text.strip():
            return text

        log_mode, log_limit, _log_ctx = _get_log_config()
        log_input = _format_log_text(text, log_mode, log_limit)
        if log_input is not None:
            logger.info(f'translate: in="{_sanitize_log_text(log_input)}"')

        start = time.perf_counter()
        logger.debug(f"translate: model={self.model} len={len(text)}")
        try:
            # Reuse batch prompt and post-processing so single-item retries
            # keep the same OCR correction behavior as batch translation.
            result_list = await self.translate_batch([text])
            result = ((result_list[0] if result_list else "") or "").strip()
            if not result:
                result = _FAILURE_MARKER
            duration_ms = (time.perf_counter() - start) * 1000
            logger.info(f"translate: ok model={self.model} ms={duration_ms:.0f} out_len={len(result)}")
            log_output = _format_log_text(result, log_mode, log_limit)
            if log_output is not None:
                logger.info(f'translate: out="{_sanitize_log_text(log_output)}"')
            return result
        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.error(f"translate: error model={self.model} ms={duration_ms:.0f} err={type(e).__name__}: {e}")
            log_output = _format_log_text(_FAILURE_MARKER, log_mode, log_limit)
            if log_output is not None:
                logger.info(f'translate: out="{_sanitize_log_text(log_output)}"')
            return _FAILURE_MARKER
    
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
                    text = getattr(response, "text", None)
                    if text is None:
                        raise RuntimeError("empty response")
                    text = str(text).strip()
                    if not text:
                        raise RuntimeError("empty response")
                    return text
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
                    content = response.choices[0].message.content
                    if content is None:
                        raise RuntimeError("empty response")
                    content = str(content).strip()
                    if not content:
                        raise RuntimeError("empty response")
                    return content
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
            text = text or ""
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
            self.last_metrics = {
                "api_calls": 0,
                "api_calls_fallback": 0,
                "slices": 0,
                "items_total": len(texts),
                "items_translated": 0,
                "prompt_chars_total": 0,
                "content_chars_total": 0,
                "text_chars_total": 0,
                "ctx_chars_total": 0,
                "duration_ms": 0,
            }
            return ["" for _ in texts]

        log_mode, log_limit, log_ctx = _get_log_config()
        batch_start = time.perf_counter()
        
        target_name = self._get_lang_name(self.target_lang)
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
        api_calls_primary = 0
        api_calls_fallback = 0
        prompt_chars_total = 0
        content_chars_total = 0
        text_chars_total = 0
        ctx_chars_total = 0
        # When the model returns numbered output but misses some indices (often due to truncation),
        # retry the same batch once with stricter formatting instructions and a larger max_tokens
        # headroom. This is usually faster/more stable than letting downstream mark them failed and
        # triggering per-item fallbacks.
        class _MissingNumberedItems(Exception):
            def __init__(self, missing: int):
                super().__init__(f"missing numbered items: {missing}")
                self.missing = missing

        async def _translate_pairs(
            pairs: list[tuple[int, str]],
            slice_idx: int | None = None,
            slice_total: int | None = None,
        ) -> list[tuple[int, str]]:
            nonlocal api_calls_primary, api_calls_fallback
            nonlocal prompt_chars_total, content_chars_total, text_chars_total, ctx_chars_total
            numbered_texts = "\n".join(
                _format_entry(i + 1, t, cleaned_contexts[orig_idx])
                for i, (orig_idx, t) in enumerate(pairs)
            )
            prompt = f"""# Role
你是一位资深的**漫画/汉化组翻译专家**，精通多国语言与{target_name}的文化转换。

# OCR 纠错
以下文本为OCR提取结果，可能存在识别错误、缺字或错字。你会看到每条文本的可选上下文(CTX)，来自同页相邻 1-2 个气泡。
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
            prompt_len = len(prompt)
            content_len = len(numbered_texts)
            slice_text_chars = sum(len(t) for _orig_idx, t in pairs)
            slice_ctx_chars = sum(len(cleaned_contexts[orig_idx]) for orig_idx, _t in pairs)

            slice_note = ""
            if slice_idx is not None and slice_total:
                slice_note = f" slice={slice_idx + 1}/{slice_total}"
            logger.info(
                f"batch: model={self.model} count={len(pairs)} total_len={len(numbered_texts)}{slice_note}"
            )
            force_strict_output = False
            for attempt in range(max_retries + 1):
                try:
                    start = time.perf_counter()
                    base_max_tokens = _estimate_batch_max_tokens(
                        item_count=len(pairs),
                        total_chars=len(numbered_texts),
                    )
                    max_tokens = base_max_tokens
                    prompt_to_use = prompt
                    if force_strict_output:
                        hard_cap = _read_env_int("AI_TRANSLATE_BATCH_MAX_TOKENS", 4000)
                        min_tokens = _read_env_int("AI_TRANSLATE_BATCH_MAX_TOKENS_MIN", 320)
                        bonus = _read_env_int(
                            "AI_TRANSLATE_BATCH_MAX_TOKENS_MISSING_NUMBER_BONUS",
                            800,
                        )
                        max_tokens = max(min_tokens, min(hard_cap, base_max_tokens + bonus))
                        prompt_to_use = (
                            prompt
                            + "\n\n# 输出格式严格要求\n"
                            + f"你必须输出 1..{len(pairs)} 共 {len(pairs)} 行，每行以 `n.` 开头，禁止漏号。"
                        )
                    prompt_len = len(prompt_to_use)
                    # Count prompt/content sizes per attempt (retries included) so we can
                    # explain latency and provider behavior post-hoc.
                    prompt_chars_total += prompt_len
                    content_chars_total += content_len
                    text_chars_total += slice_text_chars
                    ctx_chars_total += slice_ctx_chars
                    api_calls_primary += 1
                    result = await self._call_api_with_timeout(
                        prompt_to_use, max_tokens=max_tokens
                    )
                    # Defensive: some providers can return empty/None text without raising.
                    # Treat this as transient overload so fallback chain can take over.
                    if result is None:
                        raise RuntimeError("empty response")
                    if not isinstance(result, str):
                        raise RuntimeError(f"empty response (type={type(result).__name__})")
                    result = result.strip()
                    if not result:
                        raise RuntimeError("empty response")
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

                    # Retry if numbered output misses indices; otherwise downstream will mark them
                    # as failures and trigger per-item fallback, which is slower and less stable.
                    if has_numbered:
                        missing = sum(1 for t in translations if not (t or "").strip())
                        if missing:
                            raise _MissingNumberedItems(missing)

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
                    _cjk_check = _re.compile(r"[\u4e00-\u9fff]")
                    target_is_zh = str(self.target_lang or "").lower().startswith("zh")
                    for (orig_idx, orig_text), trans in zip(pairs, translations):
                        cleaned = _clean_ai_annotations(trans)
                        # Empty translation means AI skipped this number
                        if not cleaned.strip():
                            slice_results.append((orig_idx, _FAILURE_MARKER))
                        # For zh targets, never let Hangul leak into output. If the provider
                        # returns Hangul (often alongside meta/analysis text), mark it as failed
                        # so upstream fallback can retry or keep original art/text.
                        elif target_is_zh and _hangul_check.search(cleaned):
                            logger.warning(
                                "AI returned Hangul for zh target, marking as failed"
                            )
                            slice_results.append((orig_idx, _FAILURE_MARKER))
                        # For zh targets, if the source contains Hangul but the output has no CJK,
                        # treat it as invalid (e.g. analysis/formatting noise) and mark as failed.
                        elif (
                            target_is_zh
                            and _hangul_check.search(orig_text or "")
                            and not _cjk_check.search(cleaned)
                        ):
                            logger.warning(
                                "AI returned non-CJK for Hangul source under zh target, marking as failed"
                            )
                            slice_results.append((orig_idx, _FAILURE_MARKER))
                        # Detect Korean text returned unchanged (AI failed to translate names)
                        elif _hangul_check.search(cleaned) and cleaned.strip() == orig_text.strip():
                            logger.warning(f"AI returned Korean unchanged: {orig_text}")
                            slice_results.append((orig_idx, _FAILURE_MARKER))
                        else:
                            slice_results.append((orig_idx, cleaned))
                    if len(translations) < len(pairs):
                        for i in range(len(translations), len(pairs)):
                            orig_idx, orig_text = pairs[i]
                            slice_results.append((orig_idx, _FAILURE_MARKER))

                    logger.info(
                        f"batch: ok model={self.model} ms={duration_ms:.0f} out_count={len(slice_results)}{slice_note}"
                    )
                    if log_mode != "off":
                        orig_text_map = {orig_idx: orig_text for orig_idx, orig_text in pairs}
                        for orig_idx, trans in slice_results:
                            orig_text = orig_text_map.get(orig_idx, "")
                            log_in = _format_log_text(orig_text, log_mode, log_limit)
                            log_out = _format_log_text(trans, log_mode, log_limit)
                            if log_in is None and log_out is None:
                                continue
                            ctx_suffix = ""
                            if log_ctx:
                                ctx_text = cleaned_contexts[orig_idx]
                                log_ctx_text = _format_log_text(ctx_text, log_mode, log_limit)
                                if log_ctx_text is not None:
                                    ctx_suffix = f' ctx="{_sanitize_log_text(log_ctx_text)}"'
                            if log_in is None:
                                log_in = ""
                            if log_out is None:
                                log_out = ""
                            logger.info(
                                f'batch[{orig_idx + 1}]: in="{_sanitize_log_text(log_in)}" '
                                f'out="{_sanitize_log_text(log_out)}"{ctx_suffix}'
                            )
                    return slice_results

                except Exception as e:
                    if isinstance(e, _MissingNumberedItems) and attempt < max_retries:
                        logger.warning(
                            "batch: retry %d/%d due to missing numbered items=%d%s",
                            attempt + 1,
                            max_retries,
                            e.missing,
                            slice_note,
                        )
                        force_strict_output = True
                        continue
                    if self._is_overload_error(e):
                        for fallback_translator in self._fallback_translator_chain():
                            fallback_provider = getattr(fallback_translator, "provider", "unknown")
                            fallback_model = getattr(fallback_translator, "model", "unknown")
                            logger.warning(
                                "batch: fallback provider=%s model=%s due to primary error=%s%s",
                                fallback_provider,
                                fallback_model,
                                e,
                                slice_note,
                            )
                            try:
                                fallback_texts = [orig_text for _orig_idx, orig_text in pairs]
                                fallback_contexts = [cleaned_contexts[orig_idx] for orig_idx, _orig_text in pairs]
                                fallback_results = await fallback_translator.translate_batch(
                                    fallback_texts,
                                    output_format=output_format,
                                    contexts=fallback_contexts,
                                )
                                fallback_metrics = getattr(fallback_translator, "last_metrics", None) or {}
                                fallback_calls = fallback_metrics.get("api_calls")
                                if isinstance(fallback_calls, int) and fallback_calls >= 0:
                                    api_calls_fallback += fallback_calls
                                else:
                                    api_calls_fallback += 1
                                for key in (
                                    "prompt_chars_total",
                                    "content_chars_total",
                                    "text_chars_total",
                                    "ctx_chars_total",
                                ):
                                    value = fallback_metrics.get(key)
                                    if not isinstance(value, int) or value < 0:
                                        continue
                                    if key == "prompt_chars_total":
                                        prompt_chars_total += value
                                    elif key == "content_chars_total":
                                        content_chars_total += value
                                    elif key == "text_chars_total":
                                        text_chars_total += value
                                    elif key == "ctx_chars_total":
                                        ctx_chars_total += value
                                if len(fallback_results) == len(pairs):
                                    cleaned_results: list[tuple[int, str]] = []
                                    all_failed = True
                                    for (orig_idx, _orig_text), trans in zip(pairs, fallback_results):
                                        cleaned = _clean_ai_annotations(trans).strip() or _FAILURE_MARKER
                                        if not cleaned.startswith(_FAILURE_MARKER):
                                            all_failed = False
                                        cleaned_results.append((orig_idx, cleaned))

                                    # If a fallback returns only failure markers (common under overload),
                                    # continue down the fallback chain instead of short-circuiting.
                                    if all_failed:
                                        logger.warning(
                                            "batch: fallback returned all failures provider=%s model=%s%s",
                                            fallback_provider,
                                            fallback_model,
                                            slice_note,
                                        )
                                        continue
                                    return cleaned_results
                            except Exception as fallback_exc:
                                logger.error(
                                    "batch: fallback failed provider=%s model=%s err=%s%s",
                                    fallback_provider,
                                    fallback_model,
                                    fallback_exc,
                                    slice_note,
                                )

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
                            (orig_idx, _FAILURE_MARKER)
                            for orig_idx, orig_text in pairs
                        ]

            return [
                (orig_idx, _FAILURE_MARKER)
                for orig_idx, orig_text in pairs
            ]

        def _merge_results(result_pairs: list[tuple[int, str]]) -> list[str]:
            merged = ["" for _ in texts]
            for orig_idx, trans in result_pairs:
                merged[orig_idx] = trans
            return merged

        def _all_failed(result_pairs: list[tuple[int, str]]) -> bool:
            if not result_pairs:
                return False
            return all((trans or "").startswith("[翻译失败]") for _idx, trans in result_pairs)

        def _split_pairs(
            pairs: list[tuple[int, str]],
            *,
            max_items: int,
            max_chars: int,
        ) -> list[list[tuple[int, str]]]:
            if not pairs:
                return []
            if max_items <= 0:
                max_items = len(pairs)
            if max_chars <= 0:
                return [pairs[i : i + max_items] for i in range(0, len(pairs), max_items)]

            slices: list[list[tuple[int, str]]] = []
            cur: list[tuple[int, str]] = []
            cur_chars = 0
            for orig_idx, text in pairs:
                # Estimate chars in numbered_texts for this entry (exclude static prompt boilerplate).
                ctx = cleaned_contexts[orig_idx]
                entry = _format_entry(len(cur) + 1, text, ctx)
                entry_len = len(entry) + 1  # + newline

                # Close current slice if adding this entry would exceed budget (or max items).
                if cur and (len(cur) >= max_items or (cur_chars + entry_len) > max_chars):
                    slices.append(cur)
                    cur = []
                    cur_chars = 0

                cur.append((orig_idx, text))
                cur_chars += entry_len

            if cur:
                slices.append(cur)
            return slices

        async def _translate_slices(
            slices: list[list[tuple[int, str]]],
            max_concurrency: int,
        ) -> list[tuple[int, str]]:
            sem = asyncio.Semaphore(max_concurrency)

            async def _run_slice(idx: int, slice_pairs: list[tuple[int, str]]):
                async with sem:
                    return await _translate_pairs(slice_pairs, idx, len(slices))

            results = await asyncio.gather(
                *[_run_slice(i, slice_pairs) for i, slice_pairs in enumerate(slices)]
            )
            flattened: list[tuple[int, str]] = []
            for slice_results in results:
                flattened.extend(slice_results)
            return flattened

        # Prefer single-batch by default for better latency/cost.
        chunk_size = _read_env_int("AI_TRANSLATE_BATCH_CHUNK_SIZE", 200)
        concurrency = _read_env_int("AI_TRANSLATE_BATCH_CONCURRENCY", 2)
        char_budget = _read_env_int("AI_TRANSLATE_BATCH_CHAR_BUDGET", 0)
        fallback_chunk_size = _read_env_int(
            "AI_TRANSLATE_BATCH_FALLBACK_CHUNK_SIZE",
            min(12, chunk_size),
        )

        # Build slices based on both item count and char budget (if enabled).
        if len(valid_pairs) <= chunk_size and char_budget <= 0:
            slices = [valid_pairs]
        else:
            slices = _split_pairs(
                valid_pairs,
                max_items=chunk_size,
                max_chars=char_budget,
            )

        if len(slices) == 1:
            single_results = await _translate_pairs(slices[0])
            should_fallback = (
                len(valid_pairs) > 1
                and fallback_chunk_size < len(valid_pairs)
                and _all_failed(single_results)
            )
            if should_fallback:
                logger.warning(
                    "batch: full batch failed, fallback chunk_size=%d concurrency=%d",
                    fallback_chunk_size,
                    concurrency,
                )
                fallback_slices = _split_pairs(
                    valid_pairs,
                    max_items=fallback_chunk_size,
                    max_chars=char_budget,
                )
                chunked_results = await _translate_slices(fallback_slices, concurrency)
                duration_ms = (time.perf_counter() - batch_start) * 1000
                self.last_metrics = {
                    "api_calls": api_calls_primary,
                    "api_calls_fallback": api_calls_fallback,
                    "slices": len(fallback_slices),
                    "items_total": len(texts),
                    "items_translated": len(valid_pairs),
                    "prompt_chars_total": prompt_chars_total,
                    "content_chars_total": content_chars_total,
                    "text_chars_total": text_chars_total,
                    "ctx_chars_total": ctx_chars_total,
                    "chunk_size": chunk_size,
                    "char_budget": char_budget,
                    "concurrency": concurrency,
                    "fallback_chunk_size": fallback_chunk_size,
                    "duration_ms": round(duration_ms, 2),
                }
                return _merge_results(chunked_results)
            duration_ms = (time.perf_counter() - batch_start) * 1000
            self.last_metrics = {
                "api_calls": api_calls_primary,
                "api_calls_fallback": api_calls_fallback,
                "slices": len(slices),
                "items_total": len(texts),
                "items_translated": len(valid_pairs),
                "prompt_chars_total": prompt_chars_total,
                "content_chars_total": content_chars_total,
                "text_chars_total": text_chars_total,
                "ctx_chars_total": ctx_chars_total,
                "chunk_size": chunk_size,
                "char_budget": char_budget,
                "concurrency": concurrency,
                "fallback_chunk_size": fallback_chunk_size,
                "duration_ms": round(duration_ms, 2),
            }
            return _merge_results(single_results)

        chunked_results = await _translate_slices(slices, concurrency)
        duration_ms = (time.perf_counter() - batch_start) * 1000
        self.last_metrics = {
            "api_calls": api_calls_primary,
            "api_calls_fallback": api_calls_fallback,
            "slices": len(slices),
            "items_total": len(texts),
            "items_translated": len(valid_pairs),
            "prompt_chars_total": prompt_chars_total,
            "content_chars_total": content_chars_total,
            "text_chars_total": text_chars_total,
            "ctx_chars_total": ctx_chars_total,
            "chunk_size": chunk_size,
            "char_budget": char_budget,
            "concurrency": concurrency,
            "fallback_chunk_size": fallback_chunk_size,
            "duration_ms": round(duration_ms, 2),
        }
        return _merge_results(chunked_results)


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
