import asyncio


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
    assert "上一句" in captured["prompt"]
    assert result == ["测试"]


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
