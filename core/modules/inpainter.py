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
        dilation: int = 8,  # 增大膨胀范围，确保完全擦除
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

        # 过滤掉 SFX 区域（没有 target_text 的区域不需要擦除）
        regions_to_inpaint = [r for r in context.regions if r.target_text]
        skipped_count = len(context.regions) - len(regions_to_inpaint)
        
        if skipped_count > 0:
            logger.debug(f"[{context.task_id}] 跳过 {skipped_count} 个 SFX 区域")
        
        if not regions_to_inpaint:
            logger.debug(f"[{context.task_id}] 所有区域都是 SFX，跳过擦除")
            context.inpainted_path = context.image_path
            return context

        # 生成中间文件路径（擦除后的图片）
        inpainted_path = self.output_dir / f"inpainted_{context.task_id}.png"

        # Run inpainting - 只处理有翻译的区域
        await self.inpainter.inpaint_regions(
            context.image_path,
            regions_to_inpaint,
            str(inpainted_path),
            str(self.output_dir),
            dilation=self.dilation,
        )

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(f"[{context.task_id}] Inpainter 完成: 输出 {inpainted_path.name}, 耗时 {duration_ms:.0f}ms")

        # 设置中间文件路径供 renderer 使用，但保留原始 output_path
        context.inpainted_path = str(inpainted_path)
        return context
