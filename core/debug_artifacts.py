import os
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
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

    def _draw_regions(
        self,
        image_path: str,
        regions,
        label_getter,
        color: str,
        out_path: Path,
        box_getter=None,
    ):
        img = Image.open(image_path).convert("RGB")
        draw = ImageDraw.Draw(img)
        font = self._font()
        for region in regions:
            box = box_getter(region) if box_getter else region.box_2d
            if not box:
                continue
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

    def write_grouping(self, context, image_path: str):
        if not self.enabled:
            return None
        task_dir = self._ensure_dir(context.task_id)
        out_path = task_dir / "02_grouping.png"

        def label(region):
            return str(region.region_id)[:8]

        def box_getter(region):
            return region.render_box_2d or region.box_2d

        self._draw_regions(image_path, context.regions, label, "#7B61FF", out_path, box_getter=box_getter)
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

    def write_mask(self, context):
        if not self.enabled:
            return None
        if not getattr(context, "mask_path", None):
            return None
        task_dir = self._ensure_dir(context.task_id)
        out_path = task_dir / "05_inpaint_mask.png"
        mask_img = Image.open(context.mask_path)
        mask_img.save(out_path)

        overlay_path = task_dir / "05_inpaint_mask_cc_overlay.png"
        grouped_overlay_path = task_dir / "05_inpaint_mask_cc_grouped_overlay.png"
        try:
            base_img = Image.open(context.image_path).convert("RGB") if context.image_path else mask_img.convert("RGB")
            mask_np = np.array(mask_img.convert("L"))
            binary = (mask_np > 0).astype("uint8")
            num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
            font = self._font()

            # Component-level overlay (c0/c1/...)
            cc_img = base_img.copy()
            cc_draw = ImageDraw.Draw(cc_img)
            for idx in range(1, num_labels):
                x, y, w, h, _ = stats[idx]
                x1, y1, x2, y2 = int(x), int(y), int(x + w), int(y + h)
                cc_draw.rectangle([x1, y1, x2, y2], outline="#FF00FF", width=2)
                label = f"c{idx - 1}"
                text_box = cc_draw.textbbox((0, 0), label, font=font)
                text_w = text_box[2] - text_box[0]
                text_h = text_box[3] - text_box[1]
                tx = x1
                ty = max(0, y1 - text_h - 4)
                cc_draw.rectangle([tx, ty, tx + text_w + 6, ty + text_h + 4], fill="white")
                cc_draw.text((tx + 3, ty + 2), label, font=font, fill="black")
            cc_img.save(overlay_path)

            # Grouped overlay by OCR regions
            regions = getattr(context, "regions", None) or []
            if regions:
                grouped_img = base_img.copy()
                grouped_draw = ImageDraw.Draw(grouped_img)

                def intersect_area(a, b) -> int:
                    x1 = max(a[0], b[0])
                    y1 = max(a[1], b[1])
                    x2 = min(a[2], b[2])
                    y2 = min(a[3], b[3])
                    if x2 <= x1 or y2 <= y1:
                        return 0
                    return (x2 - x1) * (y2 - y1)

                region_entries = []
                for region in regions:
                    box = region.render_box_2d or region.box_2d
                    if not box:
                        continue
                    region_entries.append((str(region.region_id), (box.x1, box.y1, box.x2, box.y2)))

                group_map = {}
                unassigned = []
                for idx in range(1, num_labels):
                    x, y, w, h, _ = stats[idx]
                    comp_box = (int(x), int(y), int(x + w), int(y + h))
                    comp_area = max(1, w * h)
                    best_region = None
                    best_overlap = 0
                    for region_id, rbox in region_entries:
                        overlap = intersect_area(comp_box, rbox)
                        if overlap > best_overlap:
                            best_overlap = overlap
                            best_region = region_id
                    if best_region and (best_overlap / comp_area) >= 0.02:
                        group_map.setdefault(best_region, []).append((idx, comp_box))
                    else:
                        unassigned.append((idx, comp_box))

                if unassigned:
                    group_map.setdefault("unassigned", []).extend(unassigned)

                # Draw components in grouped overlay for context
                for idx, comp_box in [(i, b) for comps in group_map.values() for i, b in comps]:
                    x1, y1, x2, y2 = comp_box
                    grouped_draw.rectangle([x1, y1, x2, y2], outline="#B000FF", width=1)
                    label = f"c{idx - 1}"
                    text_box = grouped_draw.textbbox((0, 0), label, font=font)
                    text_w = text_box[2] - text_box[0]
                    text_h = text_box[3] - text_box[1]
                    tx = x1
                    ty = max(0, y1 - text_h - 4)
                    grouped_draw.rectangle([tx, ty, tx + text_w + 6, ty + text_h + 4], fill="white")
                    grouped_draw.text((tx + 3, ty + 2), label, font=font, fill="black")

                # Draw group boxes + labels
                sorted_groups = []
                for region_id, comps in group_map.items():
                    xs = [b[0] for _, b in comps] + [b[2] for _, b in comps]
                    ys = [b[1] for _, b in comps] + [b[3] for _, b in comps]
                    gbox = (min(xs), min(ys), max(xs), max(ys))
                    sorted_groups.append((region_id, gbox))
                sorted_groups.sort(key=lambda item: (item[1][1], item[1][0]))

                for g_idx, (region_id, gbox) in enumerate(sorted_groups):
                    x1, y1, x2, y2 = gbox
                    grouped_draw.rectangle([x1, y1, x2, y2], outline="#00C48C", width=3)
                    rid = region_id if region_id == "unassigned" else region_id.split("-")[0]
                    label = f"g{g_idx}:{rid}"
                    text_box = grouped_draw.textbbox((0, 0), label, font=font)
                    text_w = text_box[2] - text_box[0]
                    text_h = text_box[3] - text_box[1]
                    tx = x1
                    ty = max(0, y1 - text_h - 4)
                    grouped_draw.rectangle([tx, ty, tx + text_w + 6, ty + text_h + 4], fill="white")
                    grouped_draw.text((tx + 3, ty + 2), label, font=font, fill="black")

                grouped_img.save(grouped_overlay_path)
        except Exception:
            # Debug overlay is best-effort; keep mask output even if overlay fails.
            pass
        return out_path

    def write_inpainted(self, context):
        if not self.enabled:
            return None
        if not getattr(context, "inpainted_path", None):
            return None
        task_dir = self._ensure_dir(context.task_id)
        out_path = task_dir / "06_inpainted.png"
        Image.open(context.inpainted_path).save(out_path)
        return out_path

    def write_layout(self, context, image_path: str):
        if not self.enabled:
            return None
        task_dir = self._ensure_dir(context.task_id)
        out_path = task_dir / "07_layout.png"

        def label(region):
            return self._truncate(region.target_text or "")

        def box_getter(region):
            return region.render_box_2d or region.box_2d

        self._draw_regions(image_path, context.regions, label, "#00C48C", out_path, box_getter=box_getter)
        return out_path

    def write_final(self, context):
        if not self.enabled:
            return None
        if not getattr(context, "output_path", None):
            return None
        task_dir = self._ensure_dir(context.task_id)
        out_path = task_dir / "08_final.png"
        Image.open(context.output_path).save(out_path)
        return out_path
