import json
from pathlib import Path

import pytest

from core.metrics import PipelineMetrics, StageMetrics
from core.models import Box2D, PipelineResult, RegionData, TaskContext


def test_write_quality_report_creates_file(tmp_path, monkeypatch):
    monkeypatch.setenv("QUALITY_REPORT_DIR", str(tmp_path))

    ctx = TaskContext(
        image_path="/tmp/input.png",
        output_path="/tmp/output.png",
        source_language="en",
        target_language="zh-CN",
        regions=[
            RegionData(
                box_2d=Box2D(x1=0, y1=0, x2=100, y2=50),
                source_text="Hello",
                target_text="你好",
                confidence=0.9,
            )
        ],
    )

    metrics = PipelineMetrics(total_duration_ms=1234)
    metrics.add_stage(StageMetrics(name="ocr", duration_ms=100, items_processed=1))
    metrics.add_stage(StageMetrics(name="translator", duration_ms=200, items_processed=1))

    result = PipelineResult(
        success=True,
        task=ctx,
        processing_time_ms=1234,
        stages_completed=["ocr", "translator"],
        metrics=metrics.to_dict(),
    )

    from core.quality_report import write_quality_report

    report_path = write_quality_report(result)
    assert Path(report_path).exists()

    data = json.loads(Path(report_path).read_text())
    assert data["task_id"] == str(ctx.task_id)
    assert data["image_path"] == ctx.image_path
    assert data["target_language"] == "zh-CN"
    assert "timings_ms" in data
    assert data["regions"][0]["source_text"] == "Hello"
