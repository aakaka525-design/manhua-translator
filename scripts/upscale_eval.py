#!/usr/bin/env python3
import argparse
import asyncio
import json
import os
import shutil
import statistics
from datetime import datetime
from pathlib import Path

from core.models import TaskContext
from core.modules.ocr import OCRModule
from core.modules.upscaler import UpscaleModule


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def compute_stats(values):
    if not values:
        return {"avg": 0.0, "median": 0.0, "count": 0}
    return {
        "avg": sum(values) / len(values),
        "median": statistics.median(values),
        "count": len(values),
    }


def gain_ratio(old, new):
    if old <= 0:
        return 0.0
    return (new - old) / old


async def ocr_confidence(image_path: Path, lang: str) -> dict:
    ocr = OCRModule(lang=lang)
    ctx = TaskContext(image_path=str(image_path), source_language=lang)
    ctx = await ocr.process(ctx)
    confs = [r.confidence for r in (ctx.regions or []) if r.confidence is not None]
    return compute_stats(confs)


def _collect_images(input_path: Path):
    if input_path.is_file():
        return [input_path]
    items = []
    for path in input_path.rglob("*"):
        if path.suffix.lower() in IMAGE_EXTS:
            items.append(path)
    return sorted(items)


async def run_eval(input_path: Path, lang: str, out_dir: Path, min_gain: float) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    upscaled_dir = out_dir / "upscaled"
    upscaled_dir.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("UPSCALE_ENABLE", "1")

    results = []
    for image in _collect_images(input_path):
        before = await ocr_confidence(image, lang)

        upscaled_path = upscaled_dir / image.name
        shutil.copy2(image, upscaled_path)

        ctx = TaskContext(image_path=str(image), output_path=str(upscaled_path))
        await UpscaleModule().process(ctx)

        after = await ocr_confidence(upscaled_path, lang)
        ratio = gain_ratio(before["avg"], after["avg"])

        results.append({
            "image": str(image),
            "upscaled": str(upscaled_path),
            "before": before,
            "after": after,
            "gain_ratio": ratio,
            "suggest_keep": ratio >= min_gain,
        })
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="file or directory")
    parser.add_argument("--lang", default="korean")
    parser.add_argument("--format", choices=["json", "csv"], default="json")
    parser.add_argument("--min-gain", type=float, default=0.05)
    args = parser.parse_args()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path("output/upscale_eval") / ts

    results = asyncio.run(run_eval(Path(args.input), args.lang, out_dir, args.min_gain))

    if args.format == "json":
        out_path = out_dir / "report.json"
        out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        import csv

        out_path = out_dir / "report.csv"
        with out_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["image", "upscaled", "gain_ratio", "suggest_keep"],
            )
            writer.writeheader()
            for row in results:
                writer.writerow({
                    "image": row["image"],
                    "upscaled": row["upscaled"],
                    "gain_ratio": row["gain_ratio"],
                    "suggest_keep": row["suggest_keep"],
                })

    print(f"Report written: {out_path}")


if __name__ == "__main__":
    main()
