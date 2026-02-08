"""
Updated OCR Module - Uses real PaddleOCR with metrics.

Replaces mock implementation with PaddleOCREngine.
"""

import asyncio
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

from ..models import RegionData
from ..models import TaskContext
from ..modules.base import BaseModule
from ..vision import OCREngine, PaddleOCREngine, MockOCREngine
from ..ocr_postprocessor import OCRPostProcessor
from ..watermark_detector import WatermarkDetector
from ..debug_artifacts import DebugArtifactWriter
from ..errors import OCRNoTextError
from ..vision.ocr.postprocessing import build_edge_box, match_crosspage_regions, filter_noise_regions
from PIL import Image

# 配置日志
logger = logging.getLogger(__name__)

# Global OCR gate.
# PaddleOCR has historically shown race conditions under concurrency in some setups.
# Keep default concurrency=1 (same as previous global lock), but allow opt-in parallelism
# for advanced users to reduce chapter-level tail latency.
_ocr_gate: asyncio.Semaphore | None = None
_ocr_gate_size: int | None = None


def _get_ocr_gate() -> tuple[asyncio.Semaphore, int]:
    global _ocr_gate, _ocr_gate_size
    raw = (os.getenv("OCR_MAX_CONCURRENCY") or "").strip()
    size = 1
    if raw:
        try:
            size = int(raw)
        except ValueError:
            size = 1
    # Clamp to keep memory usage predictable.
    size = max(1, min(8, size))
    if _ocr_gate is None or _ocr_gate_size != size:
        _ocr_gate = asyncio.Semaphore(size)
        _ocr_gate_size = size
    return _ocr_gate, size


class OCRModule(BaseModule):
    """
    OCR module using PaddleOCR.
    
    Falls back to mock OCR if PaddleOCR is not installed.
    
    使用 detect_and_recognize() 统一入口：
    - 支持动态切片（长图）
    - 支持 NMS 去重
    - 支持完整后处理流程
    """

    def __init__(
        self,
        lang: str = "en",
        use_mock: bool = False,
    ):
        """
        Initialize OCR module.
        
        Args:
            lang: Source language code
            use_mock: Force mock OCR (for testing)
        """
        super().__init__(name="OCR")
        self.use_mock = use_mock
        self.last_metrics: Optional[dict] = None
        
        if use_mock:
            self.engine: OCREngine = MockOCREngine()
        else:
            try:
                self.engine = PaddleOCREngine(lang=lang)
                # Test initialization
                self.engine._init_ocr()
            except Exception as e:
                print(f"PaddleOCR not available ({e}), using mock")
                self.engine = MockOCREngine()

    @staticmethod
    def _calc_band_height(image_height: int) -> int:
        if image_height <= 0:
            return 0
        base = max(128, int(image_height * 0.15))
        return min(image_height, min(base, 256))

    @staticmethod
    def _pair_id_for_regions(bottom_region, top_region) -> str:
        top_box = top_region.edge_box_2d or top_region.box_2d
        qx1 = int(top_box.x1 // 5) if top_box else ""
        qy1 = int(top_box.y1 // 5) if top_box else ""
        key = "|".join(
            [
                str(qx1),
                str(qy1),
                (top_region.source_text or "").lower().strip(),
            ]
        )
        return hashlib.md5(key.encode("utf-8")).hexdigest()[:12]

    @staticmethod
    def _env_flag(name: str, default: str = "0") -> bool:
        return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}

    def _crosspage_enabled(self) -> bool:
        return self._env_flag("OCR_CROSSPAGE_EDGE_ENABLE", "1")

    def _cache_enabled(self) -> bool:
        return self._env_flag("OCR_RESULT_CACHE_ENABLE", "1")

    def _cache_empty_results_enabled(self) -> bool:
        return self._env_flag("OCR_CACHE_EMPTY_RESULTS", "0")

    def _fail_on_empty(self) -> bool:
        return self._env_flag("OCR_FAIL_ON_EMPTY", "1")

    @staticmethod
    def _cache_dir() -> Path:
        raw = os.getenv("OCR_RESULT_CACHE_DIR", "temp/ocr_cache")
        return Path(raw).expanduser().resolve()

    @staticmethod
    def _build_cache_key(image_path: str, lang: str) -> str:
        path = Path(image_path).expanduser().resolve()
        try:
            st = path.stat()
            stat_sig = f"{st.st_size}:{st.st_mtime_ns}"
        except OSError:
            stat_sig = "missing"
        digest = hashlib.sha1(f"{path}:{lang}:{stat_sig}:v1".encode("utf-8")).hexdigest()
        return digest

    def _load_cached_regions(self, image_path: str, lang: str) -> Optional[list[RegionData]]:
        if not self._cache_enabled():
            return None
        cache_file = self._cache_dir() / f"{self._build_cache_key(image_path, lang)}.json"
        if not cache_file.exists():
            return None
        try:
            payload = json.loads(cache_file.read_text(encoding="utf-8"))
            return [RegionData.model_validate(item) for item in payload.get("regions", [])]
        except Exception as exc:
            logger.debug("OCR cache read failed: %s", exc)
            return None

    def _save_cached_regions(self, image_path: str, lang: str, regions: list[RegionData]) -> None:
        if not self._cache_enabled():
            return
        if (not regions) and (not self._cache_empty_results_enabled()):
            logger.info("OCR cache skip empty result: %s (%s)", image_path, lang)
            return
        cache_dir = self._cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / f"{self._build_cache_key(image_path, lang)}.json"
        payload = {
            "image_path": str(Path(image_path).expanduser().resolve()),
            "lang": lang,
            "regions": [r.model_dump(mode="json") for r in regions],
        }
        cache_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    async def process(self, context: TaskContext) -> TaskContext:
        """
        检测并识别图像中的文本。
        
        使用 detect_and_recognize() 统一入口，支持：
        - 动态切片（长图）
        - NMS 去重
        - 完整后处理
        
        Args:
            context: Task context with image_path
            
        Returns:
            Updated context with detected regions and source_text
        """
        if not context.image_path:
            return context

        # 根据 context.source_language 动态切换 OCR 引擎
        target_lang = context.source_language or "en"
        if hasattr(self.engine, 'lang') and self.engine.lang != target_lang:
            logger.info(f"[{context.task_id}] 切换 OCR 语言: {self.engine.lang} -> {target_lang}")
            self.engine = PaddleOCREngine(lang=target_lang)
            self.engine._init_ocr()

        logger.info(f"[{context.task_id}] OCR 开始: {context.image_path}")
        start_time = time.perf_counter()
        
        # 读取图像尺寸（用于边界带判断）
        try:
            with Image.open(context.image_path) as img:
                image_height = img.height
                image_width = img.width
        except Exception:
            image_height = 0
            image_width = 0

        cache_key = self._build_cache_key(context.image_path, target_lang)
        cached_regions = self._load_cached_regions(context.image_path, target_lang)
        cache_hit = cached_regions is not None
        logger.info(
            "[%s] OCR runtime: lang=%s size=%sx%s cache_enabled=%s cache_hit=%s cache_key=%s",
            context.task_id,
            target_lang,
            image_width,
            image_height,
            self._cache_enabled(),
            cache_hit,
            cache_key,
        )
        if cached_regions is not None:
            context.regions = cached_regions
            logger.info(
                "[%s] OCR cache hit: key=%s regions=%s",
                context.task_id,
                cache_key,
                len(context.regions),
            )
            gate_wait_ms = 0.0
            gate_size = _get_ocr_gate()[1]
        else:
            gate, gate_size = _get_ocr_gate()
            wait_start = time.perf_counter()
            await gate.acquire()
            gate_wait_ms = (time.perf_counter() - wait_start) * 1000
            try:
                # Use detect_and_recognize unified entrypoint (supports long-image tiling).
                context.regions = await self.engine.detect_and_recognize(
                    context.image_path,
                )
            finally:
                gate.release()
            # Post-process OCR text (normalize + SFX detection + locale fixes)
            OCRPostProcessor().process_regions(context.regions, lang=target_lang)
            self._save_cached_regions(context.image_path, target_lang, context.regions)

        if len(context.regions) == 0 and self._fail_on_empty():
            msg = (
                f"OCR found no text regions (lang={target_lang}, "
                f"size={image_width}x{image_height}, cache_hit={cache_hit})"
            )
            logger.warning("[%s] %s", context.task_id, msg)
            raise OCRNoTextError(msg)
        if os.getenv("DEBUG_OCR") == "1":
            logger.info(
                "[%s] OCR raw regions: %s",
                context.task_id,
                [
                    {
                        "text": r.source_text,
                        "box": r.box_2d.model_dump() if r.box_2d else None,
                        "conf": r.confidence,
                    }
                    for r in (context.regions or [])
                ],
            )

        # Cross-page context: match top/bottom edge bands with neighbor pages
        if image_height > 0 and self._crosspage_enabled():
            band_height = self._calc_band_height(image_height)
            current_path = Path(context.image_path)
            parent = current_path.parent
            try:
                current_index = int(current_path.stem)
            except ValueError:
                current_index = None

            prev_path = None
            next_path = None
            if current_index is not None:
                candidates = []
                for p in parent.iterdir():
                    if p.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                        continue
                    try:
                        idx = int(p.stem)
                    except ValueError:
                        continue
                    candidates.append((idx, p))
                candidates.sort(key=lambda x: x[0])
                for i, (idx, p) in enumerate(candidates):
                    if idx == current_index:
                        if i > 0:
                            prev_path = candidates[i - 1][1]
                        if i + 1 < len(candidates):
                            next_path = candidates[i + 1][1]
                        break

            # Build edge boxes for current regions
            top_candidates = []
            bottom_candidates = []
            for region in context.regions:
                if not region.box_2d:
                    continue
                if region.box_2d.y2 <= band_height:
                    region.edge_role = "current_top"
                    region.edge_box_2d = build_edge_box(
                        region, band_height=band_height, image_height=image_height, edge="top"
                    )
                    top_candidates.append(region)
                if region.box_2d.y1 >= image_height - band_height:
                    region.edge_role = "current_bottom"
                    region.edge_box_2d = build_edge_box(
                        region, band_height=band_height, image_height=image_height, edge="bottom"
                    )
                    bottom_candidates.append(region)

            # Match previous bottom band -> current top
            crosspage_debug = {
                "current_page": current_path.name,
                "band_height": band_height,
                "prev_page": prev_path.name if prev_path else None,
                "next_page": next_path.name if next_path else None,
                "prev_bottom": [],
                "next_top": [],
            }
            if prev_path and top_candidates and hasattr(self.engine, "detect_and_recognize_band"):
                prev_bottom_regions = await self.engine.detect_and_recognize_band(
                    str(prev_path), edge="bottom", band_height=band_height
                )
                prev_bottom_regions = filter_noise_regions(
                    prev_bottom_regions, image_height=band_height, relaxed=False
                )
                for r in prev_bottom_regions:
                    r.edge_role = "prev_bottom"
                    r.edge_box_2d = build_edge_box(
                        r, band_height=band_height, image_height=band_height, edge="bottom"
                    )
                    crosspage_debug["prev_bottom"].append(
                        {
                            "source_text": r.source_text,
                            "box_2d": r.box_2d.model_dump() if r.box_2d else None,
                        }
                    )
                for cur in top_candidates:
                    for prev in prev_bottom_regions:
                        if match_crosspage_regions(prev, cur, x_overlap=0.5, y_gap=max(5, band_height // 4)):
                            cur.skip_translation = True
                            cur.inpaint_mode = "erase"
                            cur.crosspage_pair_id = self._pair_id_for_regions(prev, cur)
                            cur.crosspage_role = "next_top"
                            break

            # Match current bottom -> next top (append context)
            if next_path and bottom_candidates and hasattr(self.engine, "detect_and_recognize_band"):
                next_top_regions = await self.engine.detect_and_recognize_band(
                    str(next_path), edge="top", band_height=band_height
                )
                next_top_regions = filter_noise_regions(
                    next_top_regions, image_height=band_height, relaxed=False
                )
                for r in next_top_regions:
                    r.edge_role = "next_top"
                    r.edge_box_2d = build_edge_box(
                        r, band_height=band_height, image_height=band_height, edge="top"
                    )
                    crosspage_debug["next_top"].append(
                        {
                            "source_text": r.source_text,
                            "box_2d": r.box_2d.model_dump() if r.box_2d else None,
                        }
                    )
                for cur in bottom_candidates:
                    for nxt in next_top_regions:
                        if match_crosspage_regions(cur, nxt, x_overlap=0.5, y_gap=max(5, band_height // 4)):
                            if cur.crosspage_texts is None:
                                cur.crosspage_texts = []
                            if nxt.source_text:
                                cur.crosspage_texts.append(nxt.source_text)
                            if cur.crosspage_pair_id is None:
                                cur.crosspage_pair_id = self._pair_id_for_regions(cur, nxt)
                                cur.crosspage_role = "current_bottom"

            if crosspage_debug["prev_page"] or crosspage_debug["next_page"]:
                context.crosspage_debug = crosspage_debug

        # Detect watermark regions (skip translation, erase inpainting)
        context.image_height = image_height
        context.image_width = image_width
        image_shape = (image_height, image_width)
        if os.getenv("DISABLE_WATERMARK") != "1":
            WatermarkDetector().detect(context.regions, image_shape=image_shape)
        try:
            DebugArtifactWriter().write_ocr(context, context.image_path)
        except Exception as exc:
            logger.debug(f"[{context.task_id}] Debug artifacts (OCR) skipped: {exc}")
        
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        # Collect metrics from engine if available
        self.last_metrics = {
            "cache_hit": bool(cache_hit),
            "gate_size": int(gate_size),
            "gate_wait_ms": round(float(gate_wait_ms), 2),
            "regions_detected": len(context.regions) if context.regions else 0,
            "duration_ms": round(duration_ms, 2),
        }
        
        # Get tile metrics from engine if available
        if hasattr(self.engine, 'last_tile_count'):
            self.last_metrics["tile_count"] = self.engine.last_tile_count
        if hasattr(self.engine, 'last_tile_avg_ms'):
            tile_avg_ms = getattr(self.engine, "last_tile_avg_ms", None)
            if tile_avg_ms is not None:
                self.last_metrics["tile_avg_ms"] = round(tile_avg_ms, 2)
        if hasattr(self.engine, "last_edge_tile_count"):
            self.last_metrics["edge_tile_count"] = getattr(self.engine, "last_edge_tile_count", None)
        if hasattr(self.engine, "last_edge_tile_avg_ms"):
            edge_avg_ms = getattr(self.engine, "last_edge_tile_avg_ms", None)
            if edge_avg_ms is not None:
                self.last_metrics["edge_tile_avg_ms"] = round(edge_avg_ms, 2)

        logger.info(f"[{context.task_id}] OCR 完成: 识别 {len(context.regions)} 个区域, 耗时 {duration_ms:.0f}ms")
        
        return context

    async def validate_input(self, context: TaskContext) -> bool:
        """Validate that image path exists."""
        return context.image_path is not None
