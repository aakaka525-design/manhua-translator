"""
Pipeline Manager - Orchestrates the translation pipeline.

Chains all processing modules together:
OCR → Translator → Inpainter → Renderer → Upscaler

Includes performance metrics collection for each stage.
"""

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Optional

from .models import PipelineResult, TaskContext, TaskStatus
from .metrics import PipelineMetrics, StageMetrics, Timer, start_metrics
from .quality_report import write_quality_report
from .crosspage_processor import apply_crosspage_split
from .utils.stderr_suppressor import suppress_native_stderr
from .modules import (
    BaseModule,
    InpainterModule,
    OCRModule,
    RendererModule,
    TranslatorModule,
    UpscaleModule,
)
from .crosspage_carryover import CrosspageCarryOverStore

# 配置日志
logger = logging.getLogger(__name__)


class Pipeline:
    """
    Translation pipeline manager.
    
    Orchestrates the flow of data through all processing stages.
    Each stage updates the TaskContext with its results.
    
    流程: OCR → Translator → Inpainter → Renderer → Upscaler
    """

    def __init__(
        self,
        ocr: Optional[BaseModule] = None,
        translator: Optional[BaseModule] = None,
        inpainter: Optional[BaseModule] = None,
        renderer: Optional[BaseModule] = None,
        upscaler: Optional[BaseModule] = None,
    ):
        """
        Initialize pipeline with modules.
        
        Args:
            ocr: OCR module (default: OCRModule) - includes detection
            translator: Translation module (default: TranslatorModule)
            inpainter: Inpainting module (default: InpainterModule)
            renderer: Rendering module (default: RendererModule)
        """
        self.ocr = ocr or OCRModule()
        self.translator = translator or TranslatorModule()
        self.inpainter = inpainter or InpainterModule()
        self.renderer = renderer or RendererModule()
        self.upscaler = upscaler or UpscaleModule()

        carry_path = os.getenv("CROSSPAGE_CARRYOVER_PATH")
        if not carry_path:
            base = Path(os.getenv("QUALITY_REPORT_DIR", "output/quality_reports"))
            carry_path = str(base / "_carryover.jsonl")
        self.translator._carryover_store = CrosspageCarryOverStore(Path(carry_path))

        self.stages = [
            ("ocr", self.ocr),
            ("translator", self.translator),
            ("inpainter", self.inpainter),
            ("renderer", self.renderer),
            ("upscaler", self.upscaler),
        ]

    async def process(
        self, 
        context: TaskContext,
        collect_metrics: bool = True,
        status_callback: Optional[callable] = None,
    ) -> PipelineResult:
        """
        Run the full translation pipeline.
        
        Args:
            context: Initial task context with image_path
            collect_metrics: Whether to collect performance metrics
            status_callback: Optional callable(stage_name, status, task_id)
            
        Returns:
            PipelineResult with success status and final context
        """
        start_time = time.time()
        # Queue wait is the time from task creation to the moment this pipeline run starts.
        # This is usually ~0 for CLI single-image runs, but can be significant in API/chapter
        # workloads when tasks wait behind concurrency semaphores.
        try:
            queue_wait_ms = max(0.0, (start_time - context.created_at.timestamp()) * 1000)
        except Exception:
            queue_wait_ms = 0.0
        stages_completed = []
        
        # Initialize metrics
        metrics = PipelineMetrics() if collect_metrics else None
        stage_timings = {}
        if metrics is not None:
            # PipelineMetrics is a dataclass; we attach this attribute without changing public APIs.
            metrics.queue_wait_ms = queue_wait_ms

        logger.info(f"[{context.task_id}] Pipeline 开始: {context.image_path}")

        try:
            context.update_status(TaskStatus.PROCESSING)
            if status_callback:
                await status_callback("init", TaskStatus.PROCESSING, context.task_id)

            for stage_name, module in self.stages:
                stage_start = time.perf_counter()
                
                try:
                    # 使用 stderr 抑制器消除 NSLog 输出
                    with suppress_native_stderr():
                        context = await module.process(context)
                except Exception as stage_error:
                    logger.error(f"[{context.task_id}] {stage_name} 阶段失败: {stage_error}")
                    raise
                
                stage_duration = (time.perf_counter() - stage_start) * 1000
                stage_timings[stage_name] = stage_duration
                stages_completed.append(stage_name)
                
                if status_callback:
                    await status_callback(stage_name, TaskStatus.PROCESSING, context.task_id)

                if metrics:
                    # Get sub-metrics from module if available
                    sub_metrics = {}
                    if hasattr(module, 'last_metrics'):
                        sub_metrics = module.last_metrics or {}
                    
                    metrics.add_stage(StageMetrics(
                        name=stage_name,
                        duration_ms=stage_duration,
                        items_processed=len(context.regions) if context.regions else 0,
                        sub_metrics=sub_metrics,
                    ))

            context.update_status(TaskStatus.COMPLETED)
            if status_callback:
                await status_callback("complete", TaskStatus.COMPLETED, context.task_id)
            
            total_time = (time.time() - start_time) * 1000
            if metrics:
                metrics.total_duration_ms = total_time
            
            logger.info(f"[{context.task_id}] Pipeline 完成: 耗时 {total_time:.0f}ms, 输出 {context.output_path}")
            
            result = PipelineResult(
                success=True,
                task=context,
                processing_time_ms=total_time,
                stages_completed=stages_completed,
            )
            
            # Attach metrics to result
            if metrics:
                result.metrics = metrics

            try:
                write_quality_report(result)
            except Exception:
                logger.exception(f"[{context.task_id}] Quality report write failed")

            return result

        except Exception as e:
            logger.error(f"[{context.task_id}] Pipeline 失败: {e}")
            error_code = getattr(e, "error_code", None) or context.error_code
            context.update_status(TaskStatus.FAILED, error=str(e), error_code=error_code)
            if status_callback:
                await status_callback("failed", TaskStatus.FAILED, context.task_id)
            
            total_time = (time.time() - start_time) * 1000
            if metrics:
                metrics.total_duration_ms = total_time
            
            result = PipelineResult(
                success=False,
                task=context,
                processing_time_ms=total_time,
                stages_completed=stages_completed,
            )
            
            if metrics:
                result.metrics = metrics

            try:
                write_quality_report(result)
            except Exception:
                logger.exception(f"[{context.task_id}] Quality report write failed")

            return result

    async def process_batch(
        self,
        contexts: list[TaskContext],
        max_concurrent: int = 5,
        status_callback: Optional[callable] = None,
    ) -> list[PipelineResult]:
        """
        Process multiple images concurrently.
        
        Args:
            contexts: List of task contexts to process
            max_concurrent: Maximum concurrent tasks
            
        Returns:
            List of pipeline results
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_with_semaphore(ctx: TaskContext) -> PipelineResult:
            async with semaphore:
                return await self.process(ctx, status_callback=status_callback)

        tasks = [process_with_semaphore(ctx) for ctx in contexts]
        return await asyncio.gather(*tasks)

    async def process_batch_crosspage(
        self,
        contexts: list[TaskContext],
        status_callback: Optional[callable] = None,
    ) -> list[TaskContext]:
        for ctx in contexts:
            ctx = await self.ocr.process(ctx)

        for i in range(len(contexts) - 1):
            await apply_crosspage_split(self.translator, contexts[i], contexts[i + 1])

        for ctx in contexts:
            ctx = await self.translator.process(ctx)

        results = []
        for ctx in contexts:
            ctx = await self.inpainter.process(ctx)
            ctx = await self.renderer.process(ctx)
            ctx = await self.upscaler.process(ctx)
            results.append(ctx)
        return results


# Convenience function
async def translate_image(
    image_path: str,
    source_lang: str = "en",
    target_lang: str = "zh-CN",
    verbose: bool = False,
) -> PipelineResult:
    """
    Translate a single image.
    
    Args:
        image_path: Path to source image
        source_lang: Source language code
        target_lang: Target language code
        verbose: Print performance metrics
        
    Returns:
        PipelineResult with translation outcome
    """
    pipeline = Pipeline()
    context = TaskContext(
        image_path=image_path,
        source_language=source_lang,
        target_language=target_lang,
    )
    result = await pipeline.process(context)
    
    if verbose and hasattr(result, 'metrics') and result.metrics:
        print(result.metrics.summary())
    
    return result
