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
