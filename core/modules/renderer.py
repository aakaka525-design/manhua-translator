"""
Renderer Module - Text rendering using core TextRenderer.

Uses the full-featured TextRenderer from core/renderer.py with:
- Dynamic font sizing (binary search)
- Chinese text wrapping with typography rules
- Stroke/outline support
- Style estimation from original image
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

from ..models import TaskContext
from ..renderer import TextRenderer
from .base import BaseModule

# 配置日志
logger = logging.getLogger(__name__)


class RendererModule(BaseModule):
    """
    Renders translated text onto the inpainted image.
    
    Uses TextRenderer with full features:
    - 动态字号（二分查找适配气泡）
    - 中文避头尾规则自动换行
    - 自动描边增强
    - 样式估算（颜色提取）
    """

    def __init__(
        self, 
        output_dir: str = "./output", 
        font_path: Optional[str] = None,
        default_font_size: int = 20,
    ):
        """
        Initialize renderer.
        
        Args:
            output_dir: Directory for final output images
            font_path: Path to CJK font file (auto-detected if None)
            default_font_size: Default font size
        """
        super().__init__(name="Renderer")
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Use TextRenderer from core/renderer.py
        self.renderer = TextRenderer(
            font_path=font_path,
            default_font_size=default_font_size,
        )

    async def process(self, context: TaskContext) -> TaskContext:
        """
        Render translated text onto image.
        
        使用 TextRenderer 进行高级排版：
        1. 动态字号适配
        2. 中文换行规则
        3. 描边增强
        
        Args:
            context: Task context with inpainted image and translations
            
        Returns:
            Updated context with final output path
        """
        if not context.regions:
            regions_to_render = []
        else:
            # Filter regions with translations
            # SFX 翻译已启用：拟声词会被翻译并渲染
            import re
            regions_to_render = []
            for region in context.regions:
                # 检查是否为抹除模式（水印处理）
                if getattr(region, "inpaint_mode", "replace") == "erase":
                    # erase 模式下，即使没有 target_text 也要包含进来
                    # 这样 Renderer 才能意识到有过 Inpainting 操作
                    # 但不需要渲染任何文字，所以 target_text 保持为空即可
                    regions_to_render.append(region)
                    continue

                if not region.target_text:
                    continue
                
                # 跳过纯数字/符号的区域（如 0005~、1234）
                src = region.source_text.strip() if region.source_text else ""
                if src and re.match(r'^[\d\W]+$', src):
                    continue
                # SFX 标记现在会被渲染（如 [SFX:沙沙] -> 沙沙）
                # 提取实际翻译文本
                if region.target_text.startswith("[SFX:") and region.target_text.endswith("]"):
                    # 移除 [SFX:...] 标记，使用实际翻译内容
                    region.target_text = region.target_text[5:-1]
                regions_to_render.append(region)

        # 如果没有设置输出路径，跳过 (单图模式下 context.output_path 可能是 None，下面会处理)
        # if not context.output_path:
        #    return context

        if context.output_path and not context.output_path.endswith(str(context.task_id)):
            final_path = Path(context.output_path)
            final_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            output_filename = f"translated_{context.task_id}.png"
            final_path = self.output_dir / output_filename

        # 如果没有需要渲染的区域，直接复制原图到输出
        if not regions_to_render:
            import shutil
            source = context.inpainted_path if context.inpainted_path and Path(context.inpainted_path).exists() else context.image_path
            shutil.copy2(source, final_path)
            context.output_path = str(final_path)
            logger.debug(f"[{context.task_id}] Renderer: 无区域需要渲染，复制原图")
            return context

        logger.info(f"[{context.task_id}] Renderer 开始: {len(regions_to_render)} 个区域")
        
        import time
        start_time = time.perf_counter()

        # Use TextRenderer for full-featured rendering
        # 优先使用擦除后的图片，如果没有则使用原图
        source_image = context.inpainted_path if context.inpainted_path and Path(context.inpainted_path).exists() else context.image_path
        await self.renderer.render(
            image_path=source_image,
            regions=regions_to_render,
            output_path=str(final_path),
            original_image_path=context.image_path,
        )

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(f"[{context.task_id}] Renderer 完成: 输出 {final_path.name}, 耗时 {duration_ms:.0f}ms")

        context.output_path = str(final_path)
        return context
