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
