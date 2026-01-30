import os
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont


class DebugArtifactWriter:
    def __init__(self, output_dir: str = "output/debug", enabled: Optional[bool] = None):
        self.enabled = enabled if enabled is not None else os.getenv("DEBUG_ARTIFACTS") == "1"
        self.output_dir = Path(output_dir)

    def _task_dir(self, task_id: str) -> Path:
        return self.output_dir / str(task_id)

    def _ensure_dir(self, task_id: str) -> Path:
        task_dir = self._task_dir(task_id)
        task_dir.mkdir(parents=True, exist_ok=True)
        return task_dir

    def _font(self) -> ImageFont.ImageFont:
        try:
            return ImageFont.load_default()
        except Exception:
            return ImageFont.load_default()

    def _truncate(self, text: str, max_len: int = 24) -> str:
        if not text:
            return ""
        text = text.replace("\n", " ").strip()
        if len(text) <= max_len:
            return text
        return text[: max_len - 1] + "…"

    def _draw_regions(self, image_path: str, regions, label_getter, color: str, out_path: Path):
        img = Image.open(image_path).convert("RGB")
        draw = ImageDraw.Draw(img)
        font = self._font()
        for region in regions:
            if not region.box_2d:
                continue
            box = region.box_2d
            draw.rectangle([box.x1, box.y1, box.x2, box.y2], outline=color, width=2)
            label = self._truncate(label_getter(region) or "")
            if label:
                text_box = draw.textbbox((0, 0), label, font=font)
                text_w = text_box[2] - text_box[0]
                text_h = text_box[3] - text_box[1]
                x = box.x1
                y = max(0, box.y1 - text_h - 4)
                draw.rectangle([x, y, x + text_w + 6, y + text_h + 4], fill="white")
                draw.text((x + 3, y + 2), label, font=font, fill="black")
        img.save(out_path)

    def write_ocr(self, context, image_path: str):
        if not self.enabled:
            return None
        task_dir = self._ensure_dir(context.task_id)
        out_path = task_dir / "01_ocr_boxes.png"

        def label(region):
            return region.normalized_text or region.source_text or ""

        self._draw_regions(image_path, context.regions, label, "#00A0FF", out_path)
        return out_path

    def write_translation(self, context, image_path: str):
        if not self.enabled:
            return None
        task_dir = self._ensure_dir(context.task_id)
        out_path = task_dir / "04_translate.png"

        def label(region):
            return region.target_text or ""

        self._draw_regions(image_path, context.regions, label, "#FF8C00", out_path)
        return out_path
