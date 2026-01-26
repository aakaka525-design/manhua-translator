"""
Updated OCR Module - Uses real PaddleOCR with metrics.

Replaces mock implementation with PaddleOCREngine.
"""

import asyncio
import logging
import time
from typing import Optional

from ..models import TaskContext
from ..modules.base import BaseModule
from ..vision import OCREngine, PaddleOCREngine, MockOCREngine

# 配置日志
logger = logging.getLogger(__name__)

# 全局 OCR 锁 - 解决 PaddleOCR 并发时的竞争条件问题
_ocr_lock = asyncio.Lock()


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
        
        # 使用全局锁确保 PaddleOCR 串行执行，避免并发竞争问题
        async with _ocr_lock:
            # 使用 detect_and_recognize 统一入口（支持长图切片）
            context.regions = await self.engine.detect_and_recognize(
                context.image_path,
            )
        
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        # Collect metrics from engine if available
        self.last_metrics = {
            "regions_detected": len(context.regions) if context.regions else 0,
            "duration_ms": round(duration_ms, 2),
        }
        
        # Get tile metrics from engine if available
        if hasattr(self.engine, 'last_tile_count'):
            self.last_metrics["tile_count"] = self.engine.last_tile_count
        if hasattr(self.engine, 'last_tile_avg_ms'):
            self.last_metrics["tile_avg_ms"] = round(self.engine.last_tile_avg_ms, 2)

        logger.info(f"[{context.task_id}] OCR 完成: 识别 {len(context.regions)} 个区域, 耗时 {duration_ms:.0f}ms")
        
        return context

    async def validate_input(self, context: TaskContext) -> bool:
        """Validate that image path exists."""
        return context.image_path is not None
