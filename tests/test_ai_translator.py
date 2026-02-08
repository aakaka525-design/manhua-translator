import asyncio
import pytest


@pytest.fixture(autouse=True)
def _ai_provider_ppio(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "ppio")


def test_format_log_text_full():
    from core.ai_translator import _format_log_text

    assert _format_log_text("hello", "full", 3) == "hello"


def test_format_log_text_snippet():
    from core.ai_translator import _format_log_text

    assert _format_log_text("abcdefghij", "snippet", 3) == "abc...hij"
    assert _format_log_text("short", "snippet", 10) == "short"


def test_format_log_text_hash():
    from core.ai_translator import _format_log_text

    result = _format_log_text("hello", "hash", 3)
    assert result.startswith("sha256:")
    assert "len=5" in result


def test_translate_batch_fallback_splits_on_slash(monkeypatch):
    monkeypatch.setenv("PPIO_API_KEY", "dummy")

    from core.ai_translator import AITranslator

    monkeypatch.setattr(AITranslator, "_init_ppio", lambda self: None)

    translator = AITranslator(model="glm-4-flash-250414", source_lang="ko", target_lang="zh")

    async def fake_call_api(prompt: str, max_tokens: int = 2000) -> str:
        return "我喜欢它 / 单方面吃亏了"

    monkeypatch.setattr(translator, "_call_api", fake_call_api)

    result = asyncio.run(translator.translate_batch(["너무 좋아", "일방적으로"]))

    assert result == ["我喜欢它", "单方面吃亏了"]


def test_translate_batch_json_prompt(monkeypatch):
    monkeypatch.setenv("PPIO_API_KEY", "dummy")

    from core.ai_translator import AITranslator

    monkeypatch.setattr(AITranslator, "_init_ppio", lambda self: None)

    translator = AITranslator(model="glm-4-flash-250414", source_lang="ko", target_lang="zh")
    captured = {}

    async def fake_call_api(prompt: str, max_tokens: int = 2000) -> str:
        captured["prompt"] = prompt
        return '1. {"top":"上","bottom":"下"}'

    monkeypatch.setattr(translator, "_call_api", fake_call_api)

    result = asyncio.run(translator.translate_batch(["跨页文本"], output_format="json"))

    assert '"top"' in captured["prompt"]
    assert '"bottom"' in captured["prompt"]
    assert result == ['{"top":"上","bottom":"下"}']


def test_translate_batch_json_parses_multiline_array(monkeypatch):
    monkeypatch.setenv("PPIO_API_KEY", "dummy")

    from core.ai_translator import AITranslator

    monkeypatch.setattr(AITranslator, "_init_ppio", lambda self: None)

    translator = AITranslator(model="glm-4-flash-250414", source_lang="ko", target_lang="zh")

    async def fake_call_api(prompt: str, max_tokens: int = 2000) -> str:
        return "1. [\n  {\"top\":\"上\",\"bottom\":\"下\"}\n]"

    monkeypatch.setattr(translator, "_call_api", fake_call_api)

    result = asyncio.run(translator.translate_batch(["跨页文本"], output_format="json"))

    assert result == ['{"top":"上","bottom":"下"}']


def test_translate_batch_includes_context_in_prompt(monkeypatch):
    monkeypatch.setenv("PPIO_API_KEY", "dummy")

    from core.ai_translator import AITranslator

    monkeypatch.setattr(AITranslator, "_init_ppio", lambda self: None)

    translator = AITranslator(model="glm-4-flash-250414", source_lang="en", target_lang="zh")
    captured = {}

    async def fake_call_api(prompt: str, max_tokens: int = 2000) -> str:
        captured["prompt"] = prompt
        return "1. 测试"

    monkeypatch.setattr(translator, "_call_api", fake_call_api)

    result = asyncio.run(
        translator.translate_batch(
            ["WHERE'S THE OLAINKEI!"],
            contexts=["上一句：我在找毯子"],
        )
    )

    assert "CTX" in captured["prompt"]
    assert "TEXT" in captured["prompt"]
    assert "英文" in captured["prompt"]
    assert "OCR提取" in captured["prompt"]
    assert "上一句" in captured["prompt"]
    assert result == ["测试"]


def test_translate_reuses_batch_path_for_ocr_correction(monkeypatch):
    monkeypatch.setenv("PPIO_API_KEY", "dummy")

    from core.ai_translator import AITranslator

    monkeypatch.setattr(AITranslator, "_init_ppio", lambda self: None)

    called = {}

    async def fake_translate_batch(self, texts, output_format="numbered", contexts=None):
        called["texts"] = texts
        return ["毯子在哪儿！"]

    monkeypatch.setattr(AITranslator, "translate_batch", fake_translate_batch)

    translator = AITranslator(model="glm-4-flash-250414", source_lang="en", target_lang="zh")
    result = asyncio.run(translator.translate("WHERE'S THE OLAINKEI!"))

    assert called["texts"] == ["WHERE'S THE OLAINKEI!"]
    assert result == "毯子在哪儿！"


def test_translate_batch_cleans_text_ctx_prefix(monkeypatch):
    monkeypatch.setenv("PPIO_API_KEY", "dummy")

    from core.ai_translator import AITranslator

    monkeypatch.setattr(AITranslator, "_init_ppio", lambda self: None)

    translator = AITranslator(model="glm-4-flash-250414", source_lang="en", target_lang="zh")

    async def fake_call_api(prompt: str, max_tokens: int = 2000) -> str:
        return "1. TEXT: 高智商\n2. CTX: 高智商 | WHERE'S THE OLAINKEI!"

    monkeypatch.setattr(translator, "_call_api", fake_call_api)

    result = asyncio.run(translator.translate_batch(["A", "B"], contexts=["上文", "下文"]))

    assert result == ["高智商", "高智商 | WHERE'S THE OLAINKEI!"]


def test_translate_batch_respects_numbered_order(monkeypatch):
    monkeypatch.setenv("PPIO_API_KEY", "dummy")

    from core.ai_translator import AITranslator

    monkeypatch.setattr(AITranslator, "_init_ppio", lambda self: None)

    translator = AITranslator(model="glm-4-flash-250414", source_lang="en", target_lang="zh")

    async def fake_call_api(prompt: str, max_tokens: int = 2000) -> str:
        return "2. 第二\n1. 第一\n3. 第三"

    monkeypatch.setattr(translator, "_call_api", fake_call_api)

    result = asyncio.run(translator.translate_batch(["one", "two", "three"]))

    assert result == ["第一", "第二", "第三"]


def test_translate_batch_chunks_and_merges(monkeypatch):
    monkeypatch.setenv("PPIO_API_KEY", "dummy")
    monkeypatch.setenv("AI_TRANSLATE_BATCH_CHUNK_SIZE", "2")
    monkeypatch.setenv("AI_TRANSLATE_BATCH_CONCURRENCY", "8")

    from core.ai_translator import AITranslator

    monkeypatch.setattr(AITranslator, "_init_ppio", lambda self: None)

    translator = AITranslator(model="glm-4-flash-250414", source_lang="en", target_lang="zh")
    calls = {"count": 0}

    async def fake_call_api(prompt: str, max_tokens: int = 2000) -> str:
        calls["count"] += 1
        import re

        # 查找 "# 待翻译文本" 部分来获取编号行
        start = prompt.find("# 待翻译文本")
        if start < 0:
            start = prompt.rfind("# 输出格式")
        section = prompt[start:] if start >= 0 else prompt
        lines = []
        for line in section.splitlines():
            match = re.match(r"^(\d+)\.\s+(.*)$", line.strip())
            if match:
                text = match.group(2).strip()
                # 跳过提示词说明行
                if text.startswith("TEXT:"):
                    text = text[5:].strip()
                if text and not text.startswith("**") and not text.startswith("请"):
                    lines.append(text)
        outputs = [f"{i + 1}. OUT:{line}" for i, line in enumerate(lines)]
        return "\n".join(outputs)

    monkeypatch.setattr(translator, "_call_api", fake_call_api)

    texts = ["A", "B", "C", "D", "E"]
    result = asyncio.run(translator.translate_batch(texts))

    assert calls["count"] == 3
    assert result == [f"OUT:{t}" for t in texts]


def test_translate_batch_single_first_then_chunk_fallback(monkeypatch):
    monkeypatch.setenv("PPIO_API_KEY", "dummy")
    monkeypatch.setenv("AI_TRANSLATE_BATCH_CHUNK_SIZE", "100")
    monkeypatch.setenv("AI_TRANSLATE_BATCH_FALLBACK_CHUNK_SIZE", "2")
    monkeypatch.setenv("AI_TRANSLATE_BATCH_CONCURRENCY", "1")

    from core.ai_translator import AITranslator

    monkeypatch.setattr(AITranslator, "_init_ppio", lambda self: None)

    translator = AITranslator(model="glm-4-flash-250414", source_lang="en", target_lang="zh")
    calls = {"count": 0}

    async def fake_call_api(prompt: str, max_tokens: int = 2000) -> str:
        calls["count"] += 1
        import re

        start = prompt.find("# 待翻译文本")
        section = prompt[start:] if start >= 0 else prompt
        lines = []
        for line in section.splitlines():
            match = re.match(r"^(\d+)\.\s+(.*)$", line.strip())
            if not match:
                continue
            text = match.group(2).strip()
            if text.startswith("TEXT:"):
                text = text[5:].strip()
            if text and not text.startswith("**") and not text.startswith("请"):
                lines.append(text)

        if len(lines) > 2:
            raise RuntimeError("503 UNAVAILABLE: model overloaded")
        return "\n".join([f"{i + 1}. OUT:{line}" for i, line in enumerate(lines)])

    monkeypatch.setattr(translator, "_call_api", fake_call_api)

    texts = ["A", "B", "C", "D", "E"]
    result = asyncio.run(translator.translate_batch(texts))

    # Full-batch retries 3 times, then fallback chunks 3 times (2+2+1).
    assert calls["count"] == 6
    assert result == [f"OUT:{t}" for t in texts]


def test_ai_provider_prefers_gemini_when_explicit(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3-flash-preview")
    monkeypatch.delenv("PPIO_API_KEY", raising=False)

    from core.ai_translator import AITranslator

    called = {"gemini": 0, "ppio": 0}
    monkeypatch.setattr(
        AITranslator,
        "_init_gemini",
        lambda self: called.__setitem__("gemini", called["gemini"] + 1),
    )
    monkeypatch.setattr(
        AITranslator,
        "_init_ppio",
        lambda self: called.__setitem__("ppio", called["ppio"] + 1),
    )

    translator = AITranslator(source_lang="en", target_lang="zh")

    assert translator.is_gemini is True
    assert translator.model == "gemini-3-flash-preview"
    assert called["gemini"] == 1
    assert called["ppio"] == 0


def test_ai_provider_prefers_ppio_when_explicit(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "ppio")
    monkeypatch.setenv("PPIO_API_KEY", "dummy")
    monkeypatch.setenv("PPIO_MODEL", "zai-org/glm-4.7-flash")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    from core.ai_translator import AITranslator

    called = {"gemini": 0, "ppio": 0}
    monkeypatch.setattr(
        AITranslator,
        "_init_gemini",
        lambda self: called.__setitem__("gemini", called["gemini"] + 1),
    )
    monkeypatch.setattr(
        AITranslator,
        "_init_ppio",
        lambda self: called.__setitem__("ppio", called["ppio"] + 1),
    )

    translator = AITranslator(source_lang="en", target_lang="zh")

    assert translator.is_gemini is False
    assert translator.model == "zai-org/glm-4.7-flash"
    assert called["ppio"] == 1
    assert called["gemini"] == 0


def test_ai_provider_requires_explicit_when_both_keys_present(monkeypatch):
    monkeypatch.setenv("PPIO_API_KEY", "dummy")
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    monkeypatch.delenv("AI_PROVIDER", raising=False)

    from core.ai_translator import AITranslator

    monkeypatch.setattr(AITranslator, "_init_gemini", lambda self: None)
    monkeypatch.setattr(AITranslator, "_init_ppio", lambda self: None)

    with pytest.raises(ValueError):
        AITranslator(source_lang="en", target_lang="zh")


def test_ai_provider_defaults_to_gemini_when_only_gemini_key(monkeypatch):
    monkeypatch.delenv("PPIO_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3-flash-preview")
    monkeypatch.delenv("AI_PROVIDER", raising=False)

    from core.ai_translator import AITranslator

    called = {"gemini": 0}
    monkeypatch.setattr(
        AITranslator,
        "_init_gemini",
        lambda self: called.__setitem__("gemini", called["gemini"] + 1),
    )

    translator = AITranslator(source_lang="en", target_lang="zh")

    assert translator.is_gemini is True
    assert translator.model == "gemini-3-flash-preview"
    assert called["gemini"] == 1


def test_translate_batch_fallback_to_ppio_on_gemini_overload(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-gemini")
    monkeypatch.setenv("PPIO_API_KEY", "dummy-ppio")
    monkeypatch.setenv("AI_TRANSLATE_FALLBACK_PROVIDER", "ppio")
    monkeypatch.setenv("AI_TRANSLATE_GEMINI_FALLBACK_MODELS", "off")

    from core.ai_translator import AITranslator

    monkeypatch.setattr(AITranslator, "_init_gemini", lambda self: None)
    monkeypatch.setattr(AITranslator, "_init_ppio", lambda self: None)

    translator = AITranslator(source_lang="en", target_lang="zh")

    async def _raise_overload(prompt: str, max_tokens: int = 2000):
        raise RuntimeError("503 UNAVAILABLE: model overloaded")

    class _FallbackTranslator:
        async def translate_batch(self, texts, output_format="numbered", contexts=None):
            return [f"FB:{t}" for t in texts]

    monkeypatch.setattr(translator, "_call_api", _raise_overload)
    monkeypatch.setattr(
        translator,
        "_get_fallback_translator",
        lambda: _FallbackTranslator(),
        raising=False,
    )

    result = asyncio.run(translator.translate_batch(["A", "B"]))
    assert result == ["FB:A", "FB:B"]


def test_translate_batch_fallback_to_ppio_on_primary_timeout(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-gemini")
    monkeypatch.setenv("PPIO_API_KEY", "dummy-ppio")
    monkeypatch.setenv("AI_TRANSLATE_FALLBACK_PROVIDER", "ppio")
    monkeypatch.setenv("AI_TRANSLATE_GEMINI_FALLBACK_MODELS", "off")
    monkeypatch.setenv("AI_TRANSLATE_PRIMARY_TIMEOUT_MS", "1")

    from core.ai_translator import AITranslator

    monkeypatch.setattr(AITranslator, "_init_gemini", lambda self: None)
    monkeypatch.setattr(AITranslator, "_init_ppio", lambda self: None)

    translator = AITranslator(source_lang="en", target_lang="zh")

    async def _slow_primary(prompt: str, max_tokens: int = 2000):
        await asyncio.sleep(0.05)
        return "1. primary"

    class _FallbackTranslator:
        async def translate_batch(self, texts, output_format="numbered", contexts=None):
            return [f"FB:{t}" for t in texts]

    monkeypatch.setattr(translator, "_call_api", _slow_primary)
    monkeypatch.setattr(
        translator,
        "_get_fallback_translator",
        lambda: _FallbackTranslator(),
        raising=False,
    )

    result = asyncio.run(translator.translate_batch(["A", "B"]))
    assert result == ["FB:A", "FB:B"]


def test_translate_batch_prefers_gemini_model_fallback_before_provider(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-gemini")
    monkeypatch.setenv("PPIO_API_KEY", "dummy-ppio")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3-flash-preview")
    monkeypatch.setenv("AI_TRANSLATE_FALLBACK_PROVIDER", "ppio")
    monkeypatch.setenv("AI_TRANSLATE_GEMINI_FALLBACK_MODELS", "gemini-2.5-flash,gemini-2.5-flash-lite")

    from core.ai_translator import AITranslator

    monkeypatch.setattr(AITranslator, "_init_gemini", lambda self: None)
    monkeypatch.setattr(AITranslator, "_init_ppio", lambda self: None)

    translator = AITranslator(source_lang="en", target_lang="zh")

    async def fake_call_api(self, prompt: str, max_tokens: int = 2000):
        if self.model == "gemini-3-flash-preview":
            raise RuntimeError("503 UNAVAILABLE: model overloaded")
        if self.model == "gemini-2.5-flash":
            return "1. GEMINI25"
        return "1. PPIO"

    monkeypatch.setattr(AITranslator, "_call_api", fake_call_api, raising=False)

    result = asyncio.run(translator.translate_batch(["A"]))
    assert result == ["GEMINI25"]


def test_estimate_batch_max_tokens_scales_with_input_size():
    from core.ai_translator import _estimate_batch_max_tokens

    small = _estimate_batch_max_tokens(item_count=1, total_chars=8)
    medium = _estimate_batch_max_tokens(item_count=6, total_chars=120)
    large = _estimate_batch_max_tokens(item_count=12, total_chars=800)

    assert small < medium < large
    assert large <= 4000


def test_translate_batch_uses_estimated_max_tokens(monkeypatch):
    monkeypatch.setenv("PPIO_API_KEY", "dummy")
    monkeypatch.setenv("AI_TRANSLATE_BATCH_MAX_TOKENS", "4000")
    monkeypatch.setattr("core.ai_translator.AITranslator._init_ppio", lambda self: None)

    from core.ai_translator import AITranslator

    translator = AITranslator(model="glm-4-flash-250414", source_lang="en", target_lang="zh")
    captured = {}

    async def fake_call_api(prompt: str, max_tokens: int = 2000) -> str:
        captured["max_tokens"] = max_tokens
        return "1. 测试"

    monkeypatch.setattr(translator, "_call_api", fake_call_api)

    result = asyncio.run(translator.translate_batch(["HELLO"]))
    assert result == ["测试"]
    assert captured["max_tokens"] < 4000


def test_translate_batch_emits_prompt_metrics(monkeypatch):
    monkeypatch.setenv("PPIO_API_KEY", "dummy")
    monkeypatch.setattr("core.ai_translator.AITranslator._init_ppio", lambda self: None)

    from core.ai_translator import AITranslator

    translator = AITranslator(model="glm-4-flash-250414", source_lang="en", target_lang="zh")
    captured = {"calls": 0, "prompt": None}

    async def fake_call_api(prompt: str, max_tokens: int = 2000) -> str:
        captured["calls"] += 1
        captured["prompt"] = prompt
        return "1. A\n2. B"

    monkeypatch.setattr(translator, "_call_api", fake_call_api)

    texts = ["one", "two"]
    contexts = ["ctx1", "ctx2"]
    result = asyncio.run(translator.translate_batch(texts, contexts=contexts))
    assert result == ["A", "B"]

    metrics = translator.last_metrics
    assert metrics["api_calls"] == 1
    assert metrics["prompt_chars_total"] == len(captured["prompt"])

    numbered_texts = "\n".join(
        [
            "1. TEXT: one\n   CTX: ctx1",
            "2. TEXT: two\n   CTX: ctx2",
        ]
    )
    assert metrics["content_chars_total"] == len(numbered_texts)
    assert metrics["text_chars_total"] == len("one") + len("two")
    assert metrics["ctx_chars_total"] == len("ctx1") + len("ctx2")


def test_translate_batch_prompt_metrics_count_retries(monkeypatch):
    monkeypatch.setenv("PPIO_API_KEY", "dummy")
    monkeypatch.setattr("core.ai_translator.AITranslator._init_ppio", lambda self: None)

    from core.ai_translator import AITranslator

    translator = AITranslator(model="glm-4-flash-250414", source_lang="en", target_lang="zh")

    # Avoid slowing test down due to retry backoff.
    async def _fast_sleep(_seconds: float):
        return None

    monkeypatch.setattr(asyncio, "sleep", _fast_sleep)

    captured = {"calls": 0, "prompt_len": None}

    async def fake_call_api(prompt: str, max_tokens: int = 2000) -> str:
        captured["calls"] += 1
        captured["prompt_len"] = len(prompt)
        if captured["calls"] == 1:
            raise Exception("boom")
        return "1. OK"

    monkeypatch.setattr(translator, "_call_api", fake_call_api)

    result = asyncio.run(translator.translate_batch(["hello"], contexts=["ctx"]))
    assert result == ["OK"]

    metrics = translator.last_metrics
    assert metrics["api_calls"] == 2
    assert metrics["prompt_chars_total"] == captured["prompt_len"] * 2
