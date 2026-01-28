from unittest.mock import AsyncMock

from core.models import Box2D, RegionData, TaskContext


def test_quality_gate_retries_low_score_region(monkeypatch):
    from core.quality_gate import QualityGate

    region = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=100, y2=50),
        source_text="Hello",
        target_text="",
        confidence=0.4,
    )
    ctx = TaskContext(image_path="/tmp/input.png", target_language="zh-CN", regions=[region])

    translator = AsyncMock()
    translator.translate_region = AsyncMock(return_value="你好")

    gate = QualityGate()
    gate.apply(ctx, translator)

    assert translator.translate_region.called
    assert ctx.regions[0].target_text == "你好"


def test_quality_gate_respects_image_retry_budget(monkeypatch):
    from core.quality_gate import QualityGate

    regions = [
        RegionData(box_2d=Box2D(x1=0, y1=0, x2=10, y2=10), source_text="A", target_text="bad", confidence=0.4),
        RegionData(box_2d=Box2D(x1=0, y1=0, x2=10, y2=10), source_text="B", target_text="bad", confidence=0.4),
        RegionData(box_2d=Box2D(x1=0, y1=0, x2=10, y2=10), source_text="C", target_text="bad", confidence=0.4),
    ]
    ctx = TaskContext(image_path="/tmp/input.png", target_language="zh-CN", regions=regions)

    translator = AsyncMock()
    translator.translate_region = AsyncMock(return_value="X")

    gate = QualityGate(retry_budget_per_image=2)
    gate.apply(ctx, translator)

    assert translator.translate_region.call_count == 2


def test_quality_gate_uses_fallback_when_available(monkeypatch):
    from core.quality_gate import QualityGate

    monkeypatch.setenv("GEMINI_API_KEY", "fake")

    region = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
        source_text="Hello",
        target_text="bad",
        confidence=0.2,
    )
    ctx = TaskContext(image_path="/tmp/input.png", target_language="zh-CN", regions=[region])

    translator = AsyncMock()
    translator.translate_region = AsyncMock(return_value="bad")
    translator.create_translator = AsyncMock(return_value=translator)

    gate = QualityGate(fallback_model="gemini")
    gate.apply(ctx, translator)

    assert translator.create_translator.called


def test_retry_prompt_template_substitution():
    from core.quality_gate import build_retry_prompt

    template = (
        "请将以下文本翻译得更简洁（不超过{max_chars}字）：\n"
        "{source_text}\n"
        "保留专有名词：{glossary_terms}\n"
        "仅输出翻译结果。"
    )
    prompt = build_retry_prompt(
        template, max_chars=10, source_text="Hello", glossary_terms="A,B"
    )
    assert "10" in prompt
    assert "Hello" in prompt
    assert "A,B" in prompt
