"""PaddleOCR engine implementation."""

import asyncio
import os
import time
from uuid import uuid4

import cv2
import numpy as np

from ...models import Box2D, RegionData
from ..tiling import get_tiling_manager
from .base import OCREngine
from .cache import get_cached_ocr
from .postprocessing import (
    filter_noise_regions,
    geometric_cluster_dedup,
    merge_line_regions_geometric,
    merge_paragraph_regions,
    merge_adjacent_text_regions,
    remove_contained_regions,
)


class PaddleOCREngine(OCREngine):
    """
    OCR engine using PaddleOCR.

    Features:
    - Multi-language support
    - OCR on whole image or ROI-based detection
    """

    def __init__(self, lang: str = "en"):
        self.lang = lang
        self._ocr = None
        self.last_tile_count = None
        self.last_tile_avg_ms = None

    def _init_ocr(self):
        if self._ocr is None:
            self._ocr = get_cached_ocr(self.lang)
        return self._ocr

    @staticmethod
    def _edge_tiles_enabled() -> bool:
        raw = os.getenv("OCR_EDGE_TILE_ENABLE", "0").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    def _min_len_for_lang(self) -> int:
        lang = (self.lang or "").lower()
        if lang in {"korean", "ko", "kr"}:
            return 1
        return 2

    def _coerce_score(self, score):
        if score is None:
            return None
        if isinstance(score, (list, tuple, np.ndarray)):
            if len(score) == 0:
                return None
            score = score[0]
        try:
            return float(score)
        except (TypeError, ValueError):
            return None

    def _box_from_any(self, box, y_offset: int):
        """Build Box2D from list/array of coords or points."""
        if box is None:
            return None

        arr = np.asarray(box)
        if arr.ndim == 1 and arr.size >= 4:
            x1, y1, x2, y2 = arr[:4]
            return Box2D(
                x1=int(x1),
                y1=int(y1) + y_offset,
                x2=int(x2),
                y2=int(y2) + y_offset,
            )

        if arr.ndim >= 2 and arr.shape[0] >= 2 and arr.shape[1] >= 2:
            xs = arr[:, 0]
            ys = arr[:, 1]
            return Box2D(
                x1=int(xs.min()),
                y1=int(ys.min()) + y_offset,
                x2=int(xs.max()),
                y2=int(ys.max()) + y_offset,
            )

        return None

    async def recognize(
        self,
        image_path: str,
        regions: list[RegionData],
    ) -> list[RegionData]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._recognize_sync, image_path, regions
        )

    def _recognize_sync(
        self,
        image_path: str,
        regions: list[RegionData],
    ) -> list[RegionData]:
        ocr = self._init_ocr()
        image = cv2.imread(image_path)
        if image is None:
            raise FileNotFoundError(f"Cannot read image: {image_path}")

        for region in regions:
            if region.box_2d is None:
                continue

            box = region.box_2d
            roi = image[box.y1 : box.y2, box.x1 : box.x2]
            if roi.size == 0:
                continue

            try:
                result = ocr.predict(roi)
                if result and len(result) > 0:
                    texts = []
                    confidences = []
                    for item in result:
                        if isinstance(item, dict):
                            rec_texts = item.get("rec_texts", [])
                            rec_scores = item.get("rec_scores", [])
                            for text, score in zip(rec_texts, rec_scores):
                                if text and text.strip():
                                    score_value = self._coerce_score(score)
                                    texts.append(text.strip())
                                    if score_value is not None:
                                        confidences.append(score_value)
                    if texts:
                        region.source_text = " ".join(texts)
                        avg_conf = (
                            sum(confidences) / len(confidences) if confidences else 0.5
                        )
                        region.confidence = (
                            min(region.confidence, avg_conf)
                            if region.confidence
                            else avg_conf
                        )
            except Exception as e:
                print(f"OCR error for region {region.region_id}: {e}")
                continue

        return regions

    async def detect_and_recognize(self, image_path: str) -> list[RegionData]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._detect_and_recognize_sync, image_path
        )

    async def detect_and_recognize_band(
        self,
        image_path: str,
        edge: str,
        band_height: int,
    ) -> list[RegionData]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._detect_and_recognize_band_sync, image_path, edge, band_height
        )

    def _detect_and_recognize_sync(self, image_path: str) -> list[RegionData]:
        ocr = self._init_ocr()
        image = cv2.imread(image_path)
        if image is None:
            raise FileNotFoundError(f"Cannot read image: {image_path}")

        height, width = image.shape[:2]
        # 禁用预处理 - 预处理可能导致区域丢失
        # processed_image = preprocess_image(image)
        processed_image = image  # 直接使用原始图像

        tiling_manager = get_tiling_manager()
        all_regions: list[RegionData] = []
        min_len = self._min_len_for_lang()

        if tiling_manager.should_tile(height):
            tiles = tiling_manager.create_tiles(processed_image)
            tile_times = []

            # 串行处理切片，避免并发导致 OCR 结果不稳定
            for tile in tiles:
                start = time.perf_counter()
                tile_regions = self._process_chunk(
                    ocr, tile.image, 0, min_len=min_len
                )
                tile_times.append((time.perf_counter() - start) * 1000)
                remapped = tiling_manager.remap_regions(tile_regions, tile)
                all_regions.extend(remapped)

            all_regions = tiling_manager.merge_regions(all_regions, iou_threshold=0.5)
            self.last_tile_count = len(tiles)
            self.last_tile_avg_ms = (
                sum(tile_times) / len(tile_times) if tile_times else 0
            )

            # Edge band OCR to catch boundary text (top/bottom)
            if self._edge_tiles_enabled():
                edge_tiles = tiling_manager.create_edge_tiles(processed_image)
                for edge_tile in edge_tiles:
                    edge_regions = self._process_chunk(
                        ocr, edge_tile.image, 0, min_score=0.4, min_len=1
                    )
                    remapped = tiling_manager.remap_regions(edge_regions, edge_tile)
                    all_regions.extend(remapped)
                all_regions = tiling_manager.merge_regions(all_regions, iou_threshold=0.5)
        else:
            all_regions = self._process_chunk(
                ocr, processed_image, 0, min_len=min_len
            )
            if width < 1200 and height < 2000:
                scale = 1.5
                scaled_image = cv2.resize(
                    processed_image,
                    None,
                    fx=scale,
                    fy=scale,
                    interpolation=cv2.INTER_CUBIC,
                )
                scaled_regions = self._process_chunk(
                    ocr, scaled_image, 0, min_len=min_len
                )
                for r in scaled_regions:
                    if r.box_2d:
                        r.box_2d = Box2D(
                            x1=int(r.box_2d.x1 / scale),
                            y1=int(r.box_2d.y1 / scale),
                            x2=int(r.box_2d.x2 / scale),
                            y2=int(r.box_2d.y2 / scale),
                        )
                all_regions.extend(scaled_regions)
                all_regions = tiling_manager.merge_regions(
                    all_regions, iou_threshold=0.5
                )

            # 简化：移除多次重复 OCR 尝试，只在区域为 0 时尝试一次 fallback
            if len(all_regions) == 0:
                # 只尝试一次：使用原始图像
                raw_regions = self._process_chunk(
                    ocr, image, 0, min_score=0.3, min_len=1
                )
                all_regions = raw_regions

            self.last_tile_count = 1
            self.last_tile_avg_ms = 0

        # 简化后处理：只做必要的过滤和排序
        filtered = filter_noise_regions(all_regions, image_height=height, relaxed=True)
        all_regions = remove_contained_regions(filtered, iou_threshold=0.5)
        all_regions = merge_adjacent_text_regions(all_regions)
        # 排序逻辑优化：引入 Y 轴容差 (Row Tolerance)
        # 避免 "좋아"(y=1539) 因为比 "너무"(y=1552) 稍高而被排在前面
        # 使用 20px 的桶进行 Y 轴归一化，同一桶内按 X 轴排序
        all_regions.sort(
            key=lambda r: (
                (r.box_2d.y1 // 20 * 20) if r.box_2d else 0,
                r.box_2d.x1 if r.box_2d else 0,
            )
        )
        return all_regions

    def _detect_and_recognize_band_sync(
        self,
        image_path: str,
        edge: str,
        band_height: int,
    ) -> list[RegionData]:
        ocr = self._init_ocr()
        image = cv2.imread(image_path)
        if image is None:
            raise FileNotFoundError(f"Cannot read image: {image_path}")

        height, width = image.shape[:2]
        band_height = max(1, min(band_height, height))

        if edge == "top":
            band = image[:band_height, :width]
        elif edge == "bottom":
            band = image[height - band_height : height, :width]
        else:
            raise ValueError(f"Unsupported edge: {edge}")

        return self._process_chunk(ocr, band, 0, min_score=0.3, min_len=1)

    def _process_chunk(
        self,
        ocr,
        chunk: np.ndarray,
        y_offset: int,
        min_score: float = 0.5,
        min_len: int = 2,
    ) -> list[RegionData]:
        regions: list[RegionData] = []

        def add_region(text, score, box_any):
            if not text or not str(text).strip():
                return
            clean = str(text).strip()
            score_value = self._coerce_score(score)
            if score_value is None:
                return
            if score_value < min_score:
                return
            if len(clean) < min_len:
                return
            if all(c in ".,;:-'\"!?()[]{}|/\\" for c in clean):
                return

            box_2d = self._box_from_any(box_any, y_offset)
            if box_2d is None:
                return

            regions.append(
                RegionData(
                    region_id=uuid4(),
                    box_2d=box_2d,
                    source_text=clean,
                    confidence=score_value,
                )
            )

        try:
            result = ocr.predict(chunk)
        except Exception:
            result = None

        if result:
            for item in result:
                if isinstance(item, dict):
                    rec_texts = item.get("rec_texts", [])
                    rec_scores = item.get("rec_scores", [])
                    rec_boxes = item.get("rec_boxes", None)
                    dt_boxes = item.get("dt_boxes", None) or item.get("det_boxes", None)
                    rec_polys = (
                        item.get("rec_polys", [])
                        or item.get("dt_polys", [])
                        or item.get("det_polys", [])
                    )

                    for i, (text, score) in enumerate(zip(rec_texts, rec_scores)):
                        box_any = None
                        if rec_boxes is not None and i < len(rec_boxes):
                            box_any = rec_boxes[i]
                        elif dt_boxes is not None and i < len(dt_boxes):
                            box_any = dt_boxes[i]
                        elif i < len(rec_polys) and len(rec_polys[i]) >= 4:
                            box_any = rec_polys[i]
                        add_region(text, score, box_any)
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    points = item[0]
                    text_score = item[1]
                    if isinstance(text_score, (list, tuple)) and len(text_score) >= 2:
                        text, score = text_score[0], text_score[1]
                        add_region(text, score, points)

        if regions:
            return regions

        try:
            legacy = ocr.ocr(chunk, det=True, rec=True, cls=False)
        except Exception:
            return regions

        if not legacy:
            return regions

        # PaddleOCR may return a list containing a single list of detections.
        # Normalize to a flat list of detections for downstream parsing.
        if (
            len(legacy) == 1
            and isinstance(legacy[0], (list, tuple))
            and legacy[0]
            and isinstance(legacy[0][0], (list, tuple))
            and len(legacy[0][0]) == 2
            and isinstance(legacy[0][0][0], (list, tuple))
        ):
            legacy = legacy[0]

        for item in legacy:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            points = item[0]
            text_score = item[1]
            if isinstance(text_score, (list, tuple)) and len(text_score) >= 2:
                text, score = text_score[0], text_score[1]
                add_region(text, score, points)

        return regions


class MockOCREngine(OCREngine):
    """Mock OCR for environments without PaddleOCR."""

    MOCK_TEXTS = [
        "Hello!",
        "What's going on?",
        "Amazing!",
        "I can't believe it!",
        "Let's go!",
        "Watch out!",
    ]

    async def recognize(
        self,
        image_path: str,
        regions: list[RegionData],
    ) -> list[RegionData]:
        import random

        for i, region in enumerate(regions):
            region.source_text = self.MOCK_TEXTS[i % len(self.MOCK_TEXTS)]
            region.confidence = random.uniform(0.85, 0.98)
        return regions

    async def detect_and_recognize(self, image_path: str) -> list[RegionData]:
        image = cv2.imread(image_path)
        if image is None:
            return []
        height, width = image.shape[:2]
        box = Box2D(
            x1=int(width * 0.2),
            y1=int(height * 0.2),
            x2=int(width * 0.8),
            y2=int(height * 0.35),
        )
        region = RegionData(
            region_id=uuid4(),
            box_2d=box,
            source_text=self.MOCK_TEXTS[0],
            confidence=0.9,
        )
        return [region]
