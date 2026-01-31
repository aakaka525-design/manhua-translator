import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List


def _resolve_output_dir() -> Path:
    env_dir = os.getenv("QUALITY_REPORT_DIR")
    base = Path(env_dir) if env_dir else Path("output") / "quality_reports"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _timings_from_metrics(metrics: Any) -> Dict[str, float]:
    if metrics is None:
        return {}
    if not isinstance(metrics, dict) and hasattr(metrics, "to_dict"):
        metrics = metrics.to_dict()
    if not isinstance(metrics, dict):
        return {}

    timings: Dict[str, float] = {}
    for stage in metrics.get("stages", []) or []:
        name = stage.get("name")
        if name:
            timings[name] = stage.get("duration_ms")
    total = metrics.get("total_duration_ms")
    if total is not None:
        timings["total"] = total
    return timings


def _sanitize_component(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9_-]+", "_", text)
    text = text.strip("_")
    return text or "unknown"


def _source_slug(image_path: str) -> str:
    p = Path(image_path)
    parts = list(p.parts)
    rel_parts: List[str] = []
    if "data" in parts:
        idx = parts.index("data")
        if idx + 1 < len(parts) and parts[idx + 1] == "raw":
            rel_parts = parts[idx + 2 :]
        else:
            rel_parts = parts[idx + 1 :]
    if not rel_parts:
        rel_parts = parts[-3:]
    if len(rel_parts) > 3:
        rel_parts = rel_parts[-3:]
    if rel_parts:
        rel_parts[-1] = Path(rel_parts[-1]).stem
    slug = "__".join(_sanitize_component(x) for x in rel_parts if x)
    if len(slug) > 120:
        slug = slug[-120:]
    return slug or _sanitize_component(p.stem)


def _evaluate_region_quality(region) -> Dict[str, object]:
    ocr_conf = region.confidence if region.confidence is not None else 0.5
    length_fit = 0.5
    glossary_cov = (
        region.glossary_cov if getattr(region, "glossary_cov", None) is not None else 1.0
    )
    punctuation_ok = 1.0
    model_conf = 0.5

    score = (
        0.35 * ocr_conf
        + 0.25 * length_fit
        + 0.20 * glossary_cov
        + 0.10 * punctuation_ok
        + 0.10 * model_conf
    )

    recs: List[str] = []
    if score < 0.55:
        recs.append("retry_translation")
    if ocr_conf < 0.6:
        recs.append("low_ocr_confidence")
    if length_fit < 0.7:
        recs.append("check_overflow")
    if (not region.is_sfx) and glossary_cov < 0.6:
        recs.append("review_glossary")

    priority = {
        "retry_translation": 0,
        "low_ocr_confidence": 1,
        "check_overflow": 2,
        "review_glossary": 3,
    }
    recs.sort(key=lambda r: priority.get(r, 999))

    return {
        "quality_score": round(score, 4),
        "quality_signals": {
            "ocr_conf": ocr_conf,
            "length_fit": length_fit,
            "glossary_cov": glossary_cov,
            "punctuation_ok": punctuation_ok,
            "model_conf": model_conf,
        },
        "recommendations": recs,
    }


def write_quality_report(result) -> str:
    ctx = result.task
    output_dir = _resolve_output_dir()
    slug = _source_slug(ctx.image_path)
    report_path = output_dir / f"{slug}__{ctx.task_id}.json"

    data = {
        "task_id": str(ctx.task_id),
        "image_path": ctx.image_path,
        "output_path": ctx.output_path,
        "target_language": ctx.target_language,
        "timings_ms": _timings_from_metrics(result.metrics),
        "regions": [],
    }
    if getattr(ctx, "crosspage_debug", None):
        data["crosspage_debug"] = ctx.crosspage_debug
    for region in ctx.regions or []:
        quality = _evaluate_region_quality(region)
        data["regions"].append(
            {
                "region_id": str(region.region_id),
                "source_text": region.source_text,
                "target_text": region.target_text,
                "confidence": region.confidence,
                "box_2d": region.box_2d.model_dump() if region.box_2d else None,
                "edge_role": getattr(region, "edge_role", None),
                "edge_box_2d": region.edge_box_2d.model_dump() if getattr(region, "edge_box_2d", None) else None,
                "skip_translation": getattr(region, "skip_translation", False),
                "is_watermark": getattr(region, "is_watermark", False),
                "inpaint_mode": getattr(region, "inpaint_mode", None),
                "crosspage_texts": getattr(region, "crosspage_texts", None),
                "crosspage_pair_id": getattr(region, "crosspage_pair_id", None),
                "crosspage_role": getattr(region, "crosspage_role", None),
                "font_size_ref": getattr(region, "font_size_ref", None),
                "font_size_used": getattr(region, "font_size_used", None),
                "font_size_relaxed": getattr(region, "font_size_relaxed", None),
                "font_size_source": getattr(region, "font_size_source", None),
                **quality,
            }
        )

    report_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return str(report_path)
