from __future__ import annotations

from pathlib import Path
import json


def _load_latest_report(report_paths: list[Path]) -> dict | None:
    if not report_paths:
        return None
    latest = max(report_paths, key=lambda p: p.stat().st_mtime)
    try:
        return json.loads(latest.read_text(encoding="utf-8"))
    except Exception:
        return None


def compute_page_status(
    report_paths: list[Path],
    translated_exists: bool,
    low_quality_threshold: float,
    low_quality_ratio: float,
) -> dict:
    if not report_paths:
        return {
            "status": "processing",
            "reason": "no_report",
            "warning": False,
            "warning_counts": {"retranslate": 0, "low_quality": 0, "low_ocr": 0},
        }

    report = _load_latest_report(report_paths)
    if not report:
        return {
            "status": "processing",
            "reason": "invalid_report",
            "warning": False,
            "warning_counts": {"retranslate": 0, "low_quality": 0, "low_ocr": 0},
        }

    regions = report.get("regions") or []
    if len(regions) == 0:
        return {
            "status": "no_text",
            "reason": "regions_empty",
            "warning": False,
            "warning_counts": {"retranslate": 0, "low_quality": 0, "low_ocr": 0},
        }

    retranslate = 0
    low_quality = 0
    low_ocr = 0
    for region in regions:
        recs = region.get("recommendations") or []
        if "retranslate" in recs:
            retranslate += 1
        quality_score = region.get("quality_score")
        if quality_score is not None and quality_score < low_quality_threshold:
            low_quality += 1
        confidence = region.get("confidence")
        if confidence is not None and confidence < 0.6:
            low_ocr += 1

    warn = False
    if retranslate > 0:
        warn = True
    elif regions and (low_quality / max(1, len(regions))) >= low_quality_ratio:
        warn = True

    if warn:
        return {
            "status": "warning",
            "reason": "quality",
            "warning": True,
            "warning_counts": {
                "retranslate": retranslate,
                "low_quality": low_quality,
                "low_ocr": low_ocr,
            },
        }

    return {
        "status": "success" if translated_exists else "processing",
        "reason": "ok" if translated_exists else "no_output",
        "warning": False,
        "warning_counts": {
            "retranslate": retranslate,
            "low_quality": low_quality,
            "low_ocr": low_ocr,
        },
    }
