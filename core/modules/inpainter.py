"""
Updated Inpainter Module - Uses real inpainting.

Replaces mock implementation with LaMa/OpenCV inpainter.
"""

import logging
from pathlib import Path
from typing import Optional

from ..models import TaskContext
from ..modules.base import BaseModule
from ..vision import Inpainter, create_inpainter
from ..debug_artifacts import DebugArtifactWriter

# 配置日志
logger = logging.getLogger(__name__)


class InpainterModule(BaseModule):
    """
    Inpainting module using LaMa or OpenCV.
    
    Automatically falls back to OpenCV if LaMa is not available.
    """

    def __init__(
        self,
        inpainter: Optional[Inpainter] = None,
        output_dir: str = "./temp",
        dilation: int = 12,  # 增大膨胀范围，确保完全擦除
        prefer_lama: bool = True,
        use_time_subdir: bool = True,  # 使用时间子目录
    ):
        """
        Initialize inpainter module.
        
        Args:
            inpainter: Custom inpainter instance
            output_dir: Directory for output files
            dilation: Mask dilation in pixels (3-5 recommended)
            prefer_lama: Try LaMa first
            use_time_subdir: Create time-based subdirectory for temp files
        """
        super().__init__(name="Inpainter")
        self.inpainter = inpainter or create_inpainter(prefer_lama=prefer_lama)
        
        # 创建时间目录
        if use_time_subdir:
            from datetime import datetime
            time_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.output_dir = Path(output_dir) / time_str
        else:
            self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.dilation = dilation

    async def process(self, context: TaskContext) -> TaskContext:
        """
        Remove text from detected regions.
        
        Args:
            context: Task context with regions
            
        Returns:
            Updated context with inpainted image
        """
        if not context.regions:
            logger.debug(f"[{context.task_id}] 无区域需要擦除")
            return context

        logger.info(f"[{context.task_id}] Inpainter 开始: {len(context.regions)} 个区域")
        
        import time
        start_time = time.perf_counter()

        def _should_inpaint(region) -> bool:
            if getattr(region, "inpaint_mode", "replace") == "erase":
                return True
            if not region.target_text:
                return False
            if region.target_text.startswith("[SFX:") and region.target_text.endswith("]"):
                return False
            return True

        # 过滤掉不需要擦除的区域
        regions_to_inpaint = []
        for r in context.regions:
            if getattr(r, "inpaint_mode", "replace") == "erase":
                regions_to_inpaint.append(r)
                continue
            # 普通区域：有翻译文本且非 SFX 标记才擦除
            if r.target_text and not (r.target_text.startswith("[SFX:") and r.target_text.endswith("]")):
                regions_to_inpaint.append(r)

        skipped_count = len(context.regions) - len(regions_to_inpaint)
        
        if skipped_count > 0:
            logger.debug(f"[{context.task_id}] 跳过 {skipped_count} 个区域")
        
        if not regions_to_inpaint:
            logger.debug(f"[{context.task_id}] 所有区域无需擦除，跳过擦除")
            context.inpainted_path = context.image_path
            return context

        # 生成中间文件路径（擦除后的图片）
        inpainted_path = self.output_dir / f"inpainted_{context.task_id}.png"

        # Run inpainting - 只处理有翻译的区域
        result = await self.inpainter.inpaint_regions(
            context.image_path,
            regions_to_inpaint,
            str(inpainted_path),
            str(self.output_dir),
            dilation=self.dilation,
        )
        if isinstance(result, tuple):
            _, mask_path = result
        else:
            mask_path = None

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(f"[{context.task_id}] Inpainter 完成: 输出 {inpainted_path.name}, 耗时 {duration_ms:.0f}ms")

        # 设置中间文件路径供 renderer 使用，但保留原始 output_path
        context.inpainted_path = str(inpainted_path)
        if mask_path:
            context.mask_path = mask_path
        try:
            writer = DebugArtifactWriter()
            writer.write_mask(context)
            writer.write_inpainted(context)
        except Exception as exc:
            logger.debug(f"[{context.task_id}] Debug artifacts (Inpainter) skipped: {exc}")
        return context
