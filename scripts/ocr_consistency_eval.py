#!/usr/bin/env python3
import argparse
import asyncio
import json
import statistics
from datetime import datetime
from pathlib import Path

import cv2

from core.models import Box2D, RegionData
from core.ocr_consistency_eval import normalize_for_compare, levenshtein_ratio
from core.vision import PaddleOCREngine


def _load_image_shape(image_path: Path) -> tuple[int, int]:
    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")
    height, width = image.shape[:2]
    return height, width


def _clamp(val: int, lo: int, hi: int) -> int:
    return max(lo, min(val, hi))


def _map_box(
    box: Box2D,
    scale_x: float,
    scale_y: float,
    max_w: int,
    max_h: int,
) -> Box2D | None:
    if max_w <= 0 or max_h <= 0:
        return None
    x1 = _clamp(int(round(box.x1 * scale_x)), 0, max_w - 1)
    y1 = _clamp(int(round(box.y1 * scale_y)), 0, max_h - 1)
    x2 = _clamp(int(round(box.x2 * scale_x)), 1, max_w)
    y2 = _clamp(int(round(box.y2 * scale_y)), 1, max_h)
    if x2 <= x1 or y2 <= y1:
        return None
    return Box2D(x1=x1, y1=y1, x2=x2, y2=y2)


async def run_eval(
    orig_path: Path,
    upscaled_path: Path,
    lang: str,
    threshold: float,
    min_box: int,
    max_samples: int,
    normalize: bool,
    engine_factory,
) -> dict:
    engine = engine_factory(lang=lang)
    orig_regions = await engine.detect_and_recognize(str(orig_path))

    orig_h, orig_w = _load_image_shape(orig_path)
    up_h, up_w = _load_image_shape(upscaled_path)
    scale_x = up_w / orig_w if orig_w else 1.0
    scale_y = up_h / orig_h if orig_h else 1.0

    mapped: list[dict] = []
    recog_regions: list[RegionData] = []
    skipped = {"no_box": 0, "empty_text": 0, "too_small": 0}

    for region in orig_regions:
        if region.box_2d is None:
            skipped["no_box"] += 1
            continue
        orig_text = (region.source_text or "").strip()
        if not orig_text:
            skipped["empty_text"] += 1
            continue
        mapped_box = _map_box(region.box_2d, scale_x, scale_y, up_w, up_h)
        if mapped_box is None:
            skipped["too_small"] += 1
            continue
        if mapped_box.width < min_box or mapped_box.height < min_box:
            skipped["too_small"] += 1
            continue
        mapped.append(
            {
                "region_id": str(region.region_id),
                "orig_text": orig_text,
                "box": mapped_box,
            }
        )
        recog_regions.append(RegionData(box_2d=mapped_box))

    if recog_regions:
        await engine.recognize(str(upscaled_path), recog_regions)

    samples = []
    similarities = []
    for item, recog_region in zip(mapped, recog_regions):
        orig_text = item["orig_text"]
        up_text = (recog_region.source_text or "").strip()
        if normalize:
            orig_norm = normalize_for_compare(orig_text)
            up_norm = normalize_for_compare(up_text)
        else:
            orig_norm = orig_text
            up_norm = up_text
        similarity = levenshtein_ratio(orig_norm, up_norm)
        similarities.append(similarity)
        samples.append(
            {
                "region_id": item["region_id"],
                "box": item["box"].model_dump(),
                "orig_text": orig_text,
                "up_text": up_text,
                "similarity": similarity,
                "match": similarity >= threshold,
            }
        )

    summary = {
        "total": len(samples),
        "matched": sum(1 for s in samples if s["match"]),
        "mismatch": sum(1 for s in samples if not s["match"]),
        "avg_similarity": sum(similarities) / len(similarities) if similarities else 0.0,
        "median_similarity": statistics.median(similarities) if similarities else 0.0,
        "min_similarity": min(similarities) if similarities else 0.0,
        "max_similarity": max(similarities) if similarities else 0.0,
        "threshold": threshold,
        "skipped": skipped,
    }

    bad_samples = [s for s in samples if not s["match"]][:max_samples]

    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "orig": str(orig_path),
        "upscaled": str(upscaled_path),
        "lang": lang,
        "normalize": normalize,
        "scale_x": scale_x,
        "scale_y": scale_y,
        "summary": summary,
        "samples": samples[:max_samples],
        "bad_samples": bad_samples,
    }


def main(argv=None, engine_factory=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--orig", required=True, help="original image path")
    parser.add_argument("--upscaled", required=True, help="upscaled image path")
    parser.add_argument("--lang", default="korean")
    parser.add_argument("--out", required=True, help="output report path")
    parser.add_argument("--threshold", type=float, default=0.85)
    parser.add_argument("--min-box", type=int, default=4)
    parser.add_argument("--max-samples", type=int, default=50)
    parser.add_argument("--no-normalize", action="store_true")
    args = parser.parse_args(argv)

    if engine_factory is None:
        engine_factory = PaddleOCREngine

    report = asyncio.run(
        run_eval(
            Path(args.orig),
            Path(args.upscaled),
            args.lang,
            args.threshold,
            args.min_box,
            args.max_samples,
            not args.no_normalize,
            engine_factory,
        )
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Report written: {out_path}")


if __name__ == "__main__":
    main()
