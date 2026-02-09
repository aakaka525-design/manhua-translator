import asyncio

from core.models import Box2D, RegionData, TaskContext
from core.modules.translator import TranslatorModule, _looks_like_prompt_artifact


class _PromptArtifactAI:
    model = "mock"

    def __init__(self):
        self.calls = 0
        self.last_metrics = None

    async def translate_batch(self, texts, output_format="numbered", contexts=None, **_):
        self.calls += 1
        self.last_metrics = {
            "api_calls": 1,
            "api_calls_fallback": 0,
            "timeouts_primary": 0,
            "fallback_provider_calls": 0,
            "missing_number_retries": 0,
        }
        if self.calls == 1:
            return [
                "你是翻译助手，请严格遵守以下规则，不要添加解释，不要添加括号，"
                "assistant 仅 output only 按顺序返回内容。"
            ]
        return ["这是修复后的中文译文。"]

    async def translate(self, text):
        return "unused"


def test_prompt_artifact_detection_excludes_short_tokens():
    assert _looks_like_prompt_artifact("A") is False
    assert _looks_like_prompt_artifact("B") is False
    assert _looks_like_prompt_artifact("K") is False
    assert _looks_like_prompt_artifact("HO") is False
    assert _looks_like_prompt_artifact("[INPAINT_ONLY]") is False
    assert _looks_like_prompt_artifact("这是正常翻译。") is False


def test_translator_sanitizes_prompt_like_artifact(monkeypatch):
    monkeypatch.setenv("BUBBLE_GROUPING", "0")
    monkeypatch.setenv("AI_TRANSLATE_ZH_SANITIZE_PROMPT_ARTIFACT", "1")
    monkeypatch.setenv("AI_TRANSLATE_ZH_SANITIZE_MAX_ITEMS", "2")

    ai = _PromptArtifactAI()
    translator = TranslatorModule(source_lang="korean", target_lang="zh-CN", use_ai=True)
    monkeypatch.setattr(translator, "_get_ai_translator", lambda: ai)

    ctx = TaskContext(image_path="/tmp/in.png", source_language="korean", target_language="zh-CN")
    ctx.regions = [
        RegionData(
            box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
            source_text="테스트 문장",
            confidence=0.9,
        )
    ]

    result = asyncio.run(translator.process(ctx))
    assert result.regions[0].target_text == "这是修复后的中文译文。"
    # One call for initial batch + one call for sanitize retry.
    assert ai.calls == 2

