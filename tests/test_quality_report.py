import asyncio
import json
from pathlib import Path

import pytest

from core.metrics import PipelineMetrics, StageMetrics
from core.models import Box2D, PipelineResult, RegionData, TaskContext
from core.modules.base import BaseModule
from core.pipeline import Pipeline


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


def test_quality_report_includes_quality_signals_and_fallback(tmp_path, monkeypatch):
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
                confidence=0.8,
            )
        ],
    )

    metrics = PipelineMetrics(total_duration_ms=100)
    result = PipelineResult(
        success=True,
        task=ctx,
        processing_time_ms=100,
        stages_completed=["ocr", "translator"],
        metrics=metrics.to_dict(),
    )

    from core.quality_report import write_quality_report

    report_path = write_quality_report(result)
    data = json.loads(Path(report_path).read_text())

    region = data["regions"][0]
    assert "quality_score" in region
    assert "quality_signals" in region
    assert region["quality_signals"]["length_fit"] == 0.5


class _NoopModule(BaseModule):
    async def process(self, context):
        return context


def _make_result(tmp_path, monkeypatch, region):
    monkeypatch.setenv("QUALITY_REPORT_DIR", str(tmp_path))
    ctx = TaskContext(
        image_path="/tmp/input.png",
        target_language="zh-CN",
        regions=[region],
    )
    metrics = PipelineMetrics(total_duration_ms=100)
    return PipelineResult(
        success=True,
        task=ctx,
        processing_time_ms=100,
        stages_completed=["ocr", "translator"],
        metrics=metrics.to_dict(),
    )


def test_quality_report_recommendations_and_order(tmp_path, monkeypatch):
    region = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=100, y2=50),
        source_text="Hello",
        target_text="H",
        confidence=0.1,
    )

    result = _make_result(tmp_path, monkeypatch, region)

    from core.quality_report import write_quality_report

    report_path = write_quality_report(result)
    data = json.loads(Path(report_path).read_text())
    recs = data["regions"][0]["recommendations"]

    assert recs[0] == "retry_translation"
    assert "low_ocr_confidence" in recs


def test_pipeline_writes_quality_report(tmp_path, monkeypatch):
    monkeypatch.setenv("QUALITY_REPORT_DIR", str(tmp_path))

    pipeline = Pipeline(
        ocr=_NoopModule(),
        translator=_NoopModule(),
        inpainter=_NoopModule(),
        renderer=_NoopModule(),
    )

    ctx = TaskContext(image_path="/tmp/input.png", target_language="zh-CN")

    asyncio.run(pipeline.process(ctx))

    report_path = tmp_path / f"{ctx.task_id}.json"
    assert report_path.exists()


def test_quality_report_skips_glossary_for_sfx(tmp_path, monkeypatch):
    monkeypatch.setenv("QUALITY_REPORT_DIR", str(tmp_path))
    ctx = TaskContext(
        image_path="/tmp/input.png",
        target_language="zh-CN",
        regions=[
            RegionData(
                box_2d=Box2D(x1=0, y1=0, x2=100, y2=50),
                source_text="BANG!",
                target_text="砰!",
                confidence=0.8,
                is_sfx=True,
                glossary_cov=0.3,
            )
        ],
    )
    metrics = PipelineMetrics(total_duration_ms=100)
    result = PipelineResult(
        success=True,
        task=ctx,
        processing_time_ms=100,
        stages_completed=["ocr", "translator"],
        metrics=metrics.to_dict(),
    )

    from core.quality_report import write_quality_report

    report_path = write_quality_report(result)
    data = json.loads(Path(report_path).read_text())
    recs = data["regions"][0]["recommendations"]

    assert "review_glossary" not in recs

    non_sfx = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=100, y2=50),
        source_text="Hello",
        target_text="你好",
        confidence=0.8,
        glossary_cov=0.3,
    )
    non_sfx_result = _make_result(tmp_path, monkeypatch, non_sfx)
    non_sfx_path = write_quality_report(non_sfx_result)
    non_sfx_data = json.loads(Path(non_sfx_path).read_text())
    non_sfx_recs = non_sfx_data["regions"][0]["recommendations"]

    assert "review_glossary" in non_sfx_recs
