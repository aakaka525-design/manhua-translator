from pathlib import Path
import json

from app.services.page_status import compute_page_status, find_translated_file


def _write_report(path: Path, regions):
    data = {
        "task_id": "t1",
        "image_path": "data/raw/x/1.jpg",
        "output_path": "output/raw/x/1.jpg",
        "target_language": "zh",
        "timings_ms": {"ocr": 1},
        "regions": regions,
    }
    path.write_text(json.dumps(data), encoding="utf-8")


def test_status_no_text(tmp_path: Path):
    report = tmp_path / "x__ch1__1__abc.json"
    _write_report(report, [])
    status = compute_page_status(
        report_paths=[report],
        translated_exists=True,
        low_quality_threshold=0.7,
        low_quality_ratio=0.3,
    )
    assert status["status"] == "no_text"


def test_status_not_started(tmp_path: Path):
    status = compute_page_status(
        report_paths=[],
        translated_exists=False,
        low_quality_threshold=0.7,
        low_quality_ratio=0.3,
    )
    assert status["status"] == "not_started"


def test_status_warning_retranslate(tmp_path: Path):
    report = tmp_path / "x__ch1__1__abc.json"
    _write_report(
        report,
        [
            {
                "source_text": "A",
                "target_text": "B",
                "quality_score": 0.9,
                "recommendations": ["retranslate"],
            }
        ],
    )
    status = compute_page_status(
        report_paths=[report],
        translated_exists=True,
        low_quality_threshold=0.7,
        low_quality_ratio=0.3,
    )
    assert status["status"] == "warning"
    assert status["warning_counts"]["retranslate"] == 1


def test_status_success(tmp_path: Path):
    report = tmp_path / "x__ch1__1__abc.json"
    _write_report(
        report,
        [
            {
                "source_text": "A",
                "target_text": "B",
                "quality_score": 0.9,
                "recommendations": [],
            }
        ],
    )
    status = compute_page_status(
        report_paths=[report],
        translated_exists=True,
        low_quality_threshold=0.7,
        low_quality_ratio=0.3,
    )
    assert status["status"] == "success"


def test_find_translated_file_prefers_webp(tmp_path: Path):
    png_path = tmp_path / "1.png"
    webp_path = tmp_path / "1.webp"
    png_path.write_bytes(b"png")
    webp_path.write_bytes(b"webp")

    picked = find_translated_file(tmp_path, "1")
    assert picked == webp_path
