"""
Translator Module - Text translation using AI or Google Translate.

Uses AI (PPIO/Gemini) or deep-translator library for real translation.
Includes SFX detection and performance metrics.
"""

import asyncio
import logging
import os
import re
import time
from typing import Optional

from ..models import TaskContext, Box2D
from .base import BaseModule

# 配置日志
logger = logging.getLogger(__name__)


# Common SFX patterns that should not be translated
SFX_PATTERNS = [
    r'^[A-Z]{1,3}$',  # Short caps like "HA", "HM"
    r'^[!?]+$',  # Punctuation only
    r'^\*+.*\*+$',  # Asterisk wrapped
    r'^(BOOM|BANG|CRASH|SLASH|WHOOSH|THUD|CRACK|THUMP|SPLASH|RUMBLE)$',  # Common SFX
    r'^(HA)+$',  # Laughter
    r'^(HE)+$',
    r'^(HO)+$',
    r'^[A-Z]{2,}!+$',  # CAPS with exclamation like "BOOM!"
]


def _is_sfx(text: str) -> bool:
    """Check if text is likely a sound effect."""
    text = text.strip().upper()
    for pattern in SFX_PATTERNS:
        if re.match(pattern, text, re.IGNORECASE):
            return True
    return False


def _should_skip_translation(text: str) -> tuple[bool, str]:
    """
    判断文本是否应跳过翻译（只过滤纯数字/符号）。
    
    Returns:
        (should_skip, reason)
    """
    if not text or not text.strip():
        return True, "空文本"
    
    text = text.strip()
    
    # 纯数字/符号（如 0005~、1234、---）
    import re
    if re.match(r'^[\d\W]+$', text):
        return True, "纯数字/符号"
    
    return False, ""


class TranslatorModule(BaseModule):
    """
    Translates source text to target language using Google Translate.
    
    Features:
    - 合并相邻区域后翻译（更好的上下文）
    - SFX 识别并标注（不翻译拟声词）
    - 使用 Google Translate API（免费）
    - 支持降级到 mock 翻译
    - 性能指标收集
    """

    def __init__(
        self,
        source_lang: str = "en",
        target_lang: str = "zh-CN",
        use_mock: bool = False,
        use_ai: bool = True,  # 默认使用 AI 翻译
    ):
        """
        Initialize translator.
        
        Args:
            source_lang: Source language code
            target_lang: Target language code (zh-CN for simplified Chinese)
            use_mock: Use mock translation (for testing)
            use_ai: Use AI translation (PPIO GLM) instead of Google Translate
        """
        super().__init__(name="Translator")
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.use_mock = use_mock
        self.use_ai = use_ai
        self._translator_class = None
        self._ai_translator = None
        self._current_model = None  # 缓存当前模型
        self.last_metrics: Optional[dict] = None
        
        if not use_mock and not use_ai:
            try:
                from deep_translator import GoogleTranslator
                self._translator_class = GoogleTranslator
            except ImportError:
                print("deep-translator not installed, using mock")
                self.use_mock = True
    
    def _get_ai_translator(self):
        """获取 AI 翻译器，支持动态模型切换。"""
        # 获取当前选择的模型
        try:
            from app.routes.settings import get_current_model
            current_model = get_current_model()
        except:
            current_model = None
        
        # 如果模型变化或未初始化，重新创建翻译器
        if self._ai_translator is None or (current_model and current_model != self._current_model):
            try:
                from ..ai_translator import AITranslator
                self._ai_translator = AITranslator(
                    self.source_lang, 
                    self.target_lang,
                    model=current_model
                )
                self._current_model = current_model
                if current_model:
                    print(f"Translator using model: {current_model}")
            except Exception as e:
                print(f"AI translator init failed: {e}")
                return None
        
        return self._ai_translator

    def create_translator(self, model_name: str):
        """创建指定模型的翻译器实例（用于 fallback）。"""
        from ..ai_translator import AITranslator
        return AITranslator(self.source_lang, self.target_lang, model=model_name)

    async def process(self, context: TaskContext) -> TaskContext:
        """
        Translate all source texts to target language.
        
        流程：
        1. 先合并相邻区域为段落
        2. 检测 SFX 并标注
        3. 使用 AI 或 Google Translate 翻译非 SFX 区域
        
        Args:
            context: Task context with source_text filled
            
        Returns:
            Updated context with target_text filled
        """
        if not context.regions:
            logger.debug(f"[{context.task_id}] 无区域需要翻译")
            self.last_metrics = {"requests": 0, "total_ms": 0, "avg_ms": 0}
            return context

        logger.info(f"[{context.task_id}] 开始翻译 {len(context.regions)} 个区域")

        # 使用分组翻译策略：分组获取上下文，批量翻译，按比例分割结果回原始区域
        from ..translator import group_adjacent_regions, split_translation_by_ratio
        
        # 1. 将相邻区域分组（保持原始区域不变）
        groups = group_adjacent_regions(context.regions)
        logger.debug(f"[{context.task_id}] 区域分组: {len(context.regions)} 个区域 -> {len(groups)} 个分组")
        debug = os.getenv("DEBUG_TRANSLATOR") == "1"
        if debug:
            logger.info(
                "[%s] Translator groups=%d",
                context.task_id,
                len(groups),
            )

        # Metrics tracking
        total_translate_ms = 0.0
        sfx_count = 0

        # 2. 准备批量翻译：收集所有分组的合并文本
        texts_to_translate = []
        groups_to_translate = []
        group_indexes = []
        
        for idx, group in enumerate(groups):
            skip_region_ids = set()
            texts = []
            for r in group:
                if not r.source_text:
                    continue
                should_skip, _ = _should_skip_translation(r.source_text)
                if should_skip:
                    skip_region_ids.add(r.region_id)
                    continue
                texts.append(r.source_text.strip())

            combined_text = " ".join(texts)
            if debug:
                logger.info(
                    "[%s] group[%d] texts=%s combined=%s skip_ids=%s watermark=%s",
                    context.task_id,
                    idx,
                    texts,
                    combined_text,
                    [str(i)[:8] for i in skip_region_ids],
                    any(getattr(r, "is_watermark", False) for r in group),
                )

            if not combined_text.strip():
                # 全部是可跳过文本，保持不渲染
                for region in group:
                    region.target_text = ""
                continue

            if any(getattr(r, "is_watermark", False) for r in group):
                for region in group:
                    region.target_text = ""
                continue
            
            # 检测是否应跳过翻译（纯数字/符号等）
            should_skip, skip_reason = _should_skip_translation(combined_text)
            if should_skip:
                for region in group:
                    region.target_text = ""  # 留空不渲染
                continue
            
            # 检测 SFX
            if _is_sfx(combined_text):
                for region in group:
                    region.target_text = f"[SFX: {region.source_text}]"
                sfx_count += len(group)
                continue
            
            texts_to_translate.append(combined_text)
            groups_to_translate.append(group)
            group_indexes.append(idx)

        # 3. 批量翻译（一次 API 调用）
        if texts_to_translate:
            try:
                if self.use_mock:
                    translations = [f"[翻译] {t}" for t in texts_to_translate]
                elif self.use_ai:
                    ai_translator = self._get_ai_translator()
                    if ai_translator:
                        start = time.perf_counter()
                        translations = await ai_translator.translate_batch(texts_to_translate)
                        total_translate_ms = (time.perf_counter() - start) * 1000
                    else:
                        translations = [f"[翻译失败] {t}" for t in texts_to_translate]
                else:
                    # Google Translate 逐个翻译
                    translations = []
                    for text in texts_to_translate:
                        translator = self._translator_class(
                            source=self.source_lang,
                            target=self.target_lang
                        )
                        start = time.perf_counter()
                        loop = asyncio.get_event_loop()
                        result = await loop.run_in_executor(None, translator.translate, text)
                        translations.append(result)
                        total_translate_ms += (time.perf_counter() - start) * 1000
                if debug:
                    logger.info(
                        "[%s] translations=%s",
                        context.task_id,
                        list(zip(group_indexes, translations)),
                    )
                
                # 4. 将翻译结果分配到原始区域
                for group, translation, group_idx in zip(groups_to_translate, translations, group_indexes):
                    if len(group) == 1:
                        # 单区域分组，直接赋值
                        group[0].target_text = translation
                        if debug:
                            logger.info(
                                "[%s] assign group[%d] single -> %s",
                                context.task_id,
                                group_idx,
                                translation,
                            )
                    else:
                        # 多区域分组：只在最大区域渲染完整翻译
                        # 其他区域设为占位符（用于 inpainting 擦除原文，但不渲染新文字）
                        xs = [r.box_2d.x1 for r in group if r.box_2d]
                        ys = [r.box_2d.y1 for r in group if r.box_2d]
                        xe = [r.box_2d.x2 for r in group if r.box_2d]
                        ye = [r.box_2d.y2 for r in group if r.box_2d]
                        render_box = None
                        if xs and ys and xe and ye:
                            render_box = Box2D(x1=min(xs), y1=min(ys), x2=max(xe), y2=max(ye))
                        non_skip = [r for r in group if r.region_id not in skip_region_ids]
                        if not non_skip:
                            for region in group:
                                region.target_text = ""
                            continue
                        largest_region = max(non_skip, key=lambda r: r.box_2d.width * r.box_2d.height)
                        for region in group:
                            if region is largest_region:
                                region.target_text = translation
                                if render_box:
                                    region.render_box_2d = render_box
                            else:
                                # 占位符：触发 inpainting 但渲染时跳过
                                region.target_text = "[INPAINT_ONLY]"
                        if debug:
                            logger.info(
                                "[%s] assign group[%d] multi -> %s (largest=%s)",
                                context.task_id,
                                group_idx,
                                translation,
                                str(largest_region.region_id)[:8],
                            )
                            
            except Exception as e:
                logger.error(f"[{context.task_id}] 翻译失败: {e}")
                for group in groups_to_translate:
                    for region in group:
                        region.target_text = f"[翻译失败] {region.source_text}"

        # 获取模型名称用于日志
        model_name = "unknown"
        if self.use_ai:
            ai_translator = self._get_ai_translator()
            if ai_translator:
                model_name = ai_translator.model
        
        translated_count = sum(1 for r in context.regions if r.target_text and not r.target_text.startswith("["))
        logger.info(f"[{context.task_id}] 翻译完成: {translated_count} 条, 模型: {model_name}, 耗时 {total_translate_ms:.0f}ms")

        # Store metrics
        self.last_metrics = {
            "requests": 1,  # 只有一次批量请求
            "total_ms": round(total_translate_ms, 2),
            "avg_ms": round(total_translate_ms / len(texts_to_translate), 2) if texts_to_translate else 0,
            "sfx_skipped": sfx_count,
        }

        return context
