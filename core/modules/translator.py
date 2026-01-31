"""
Translator Module - Text translation using AI or Google Translate.

Uses AI (PPIO/Gemini) or deep-translator library for real translation.
Includes SFX detection and performance metrics.
"""

import asyncio
import json
import logging
import os
import re
import time
from typing import Optional

from ..models import TaskContext, Box2D
from core.logging_config import setup_module_logger, get_log_level
from .base import BaseModule
from ..debug_artifacts import DebugArtifactWriter

# 配置日志
logger = setup_module_logger(
    __name__,
    "translator/translator.log",
    level=get_log_level("TRANSLATOR_LOG_LEVEL", logging.INFO),
)


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


_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_HANGUL_RE = re.compile(r"[\uac00-\ud7a3\u3130-\u318f\u1100-\u11ff]")


def _has_cjk(text: str) -> bool:
    if not text:
        return False
    # Failure marker should not block fallback
    if text.strip().startswith("[翻译失败]"):
        return False
    return bool(_CJK_RE.search(text))


def _has_hangul(text: str) -> bool:
    return bool(_HANGUL_RE.search(text or ""))


def _snippet(text: Optional[str], limit: int = 20) -> str:
    if not text:
        return ""
    return text[:limit] + ("…" if len(text) > limit else "")


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
        from ..text_merge.line_merger import merge_line_regions
        
        # 1. 将相邻区域分组（保持原始区域不变）
        raw_groups = group_adjacent_regions(context.regions)
        context.regions = merge_line_regions(raw_groups)
        groups = group_adjacent_regions(context.regions)
        logger.debug(f"[{context.task_id}] 区域分组: {len(context.regions)} 个区域 -> {len(groups)} 个分组")
        debug = os.getenv("DEBUG_TRANSLATOR") == "1"
        if debug:
            logger.info(
                "[%s] Translator groups=%d",
                context.task_id,
                len(groups),
            )
        logger.debug(f"[{context.task_id}] 翻译模块日志级别: {logger.level}")

        # Metrics tracking
        total_translate_ms = 0.0
        sfx_count = 0

        # 2. 准备批量翻译：收集所有分组的合并文本
        texts_to_translate = []
        groups_to_translate = []
        group_indexes = []
        crosspage_meta = []
        skip_region_ids_list = []

        for idx, group in enumerate(groups):
            group = [
                r for r in group if not (r.target_text and r.target_text.strip())
            ]
            if not group:
                continue
            skip_region_ids = set()

            # Consume carryover for next_top regions before translation
            for r in group:
                if getattr(r, "crosspage_role", None) == "next_top":
                    store = getattr(self, "_carryover_store", None)
                    if store and getattr(r, "crosspage_pair_id", None):
                        carried = store.consume(r.crosspage_pair_id)
                        if carried:
                            r.target_text = carried
                            r.skip_translation = True
                        else:
                            r.skip_translation = False
                    else:
                        r.skip_translation = False

            crosspage_region = None
            crosspage_extra = ""
            for r in group:
                if getattr(r, "crosspage_role", None) == "current_bottom" and getattr(
                    r, "crosspage_pair_id", None
                ):
                    crosspage_region = r
                    if getattr(r, "crosspage_texts", None):
                        crosspage_extra = " ".join(
                            t.strip() for t in r.crosspage_texts if t and t.strip()
                        )
                    break

            texts = []
            for r in group:
                if not r.source_text:
                    continue
                if getattr(r, "skip_translation", False):
                    if r.target_text:
                        continue
                    r.target_text = ""
                    continue
                should_skip, _ = _should_skip_translation(r.source_text)
                if should_skip:
                    skip_region_ids.add(r.region_id)
                    continue
                text = r.source_text.strip()
                if getattr(r, "crosspage_texts", None):
                    extra = " ".join(
                        t.strip() for t in r.crosspage_texts if t and t.strip()
                    )
                    if extra:
                        text = f"{text} {extra}".strip()
                texts.append(text)

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
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    f"[{context.task_id}] 组文本长度={len(combined_text)} "
                    f"跨页追加={bool(getattr(group[0], 'crosspage_texts', None))}"
                )
            if not combined_text.strip():
                # 全部是可跳过文本，保持不渲染（保留已填充的 carryover 文本）
                for region in group:
                    if not region.target_text:
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
            skip_region_ids_list.append(skip_region_ids)
            if crosspage_region:
                crosspage_meta.append(
                    {
                        "region": crosspage_region,
                        "extra": crosspage_extra,
                    }
                )
            else:
                crosspage_meta.append(None)

        # 3. 批量翻译（一次 API 调用）
        ai_translator = None
        if texts_to_translate:
            try:
                if self.use_mock:
                    translations = []
                    for text, meta in zip(texts_to_translate, crosspage_meta):
                        if meta and meta["region"]:
                            top = (meta["region"].source_text or "").strip()
                            bottom = (meta["extra"] or "").strip()
                            translations.append(
                                json.dumps({"top": top, "bottom": bottom}, ensure_ascii=False)
                            )
                        else:
                            translations.append(f"[翻译] {text}")
                elif self.use_ai:
                    ai_translator = self._get_ai_translator()
                    if ai_translator:
                        translations = [None] * len(texts_to_translate)
                        crosspage_indices = [
                            i for i, meta in enumerate(crosspage_meta) if meta
                        ]
                        normal_indices = [
                            i for i, meta in enumerate(crosspage_meta) if not meta
                        ]
                        if crosspage_indices:
                            crosspage_texts = [texts_to_translate[i] for i in crosspage_indices]
                            start = time.perf_counter()
                            crosspage_translations = await ai_translator.translate_batch(
                                crosspage_texts,
                                output_format="json",
                            )
                            total_translate_ms += (time.perf_counter() - start) * 1000
                            for idx, translation in zip(crosspage_indices, crosspage_translations):
                                translations[idx] = translation
                        if normal_indices:
                            normal_texts = [texts_to_translate[i] for i in normal_indices]
                            start = time.perf_counter()
                            normal_translations = await ai_translator.translate_batch(normal_texts)
                            total_translate_ms += (time.perf_counter() - start) * 1000
                            for idx, translation in zip(normal_indices, normal_translations):
                                translations[idx] = translation
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

                if self.use_ai and (self.target_lang or "").startswith("zh"):
                    ai_translator = self._get_ai_translator()
                    if ai_translator:
                        fixed_translations = []
                        for src_text, translation in zip(texts_to_translate, translations):
                            if not _has_cjk(translation):
                                try:
                                    translation = await ai_translator.translate(src_text)
                                except Exception:
                                    pass
                                if not _has_cjk(translation):
                                    gt_class = self._translator_class
                                    if gt_class is None:
                                        try:
                                            from deep_translator import GoogleTranslator
                                            gt_class = GoogleTranslator
                                        except ImportError:
                                            gt_class = None
                                    if gt_class is not None:
                                        loop = asyncio.get_event_loop()
                                        translator = gt_class(
                                            source=self.source_lang,
                                            target=self.target_lang,
                                        )
                                        try:
                                            translation = await loop.run_in_executor(
                                                None, translator.translate, src_text
                                            )
                                        except Exception:
                                            pass
                            fixed_translations.append(translation)
                        translations = fixed_translations
                
                # 4. 将翻译结果分配到原始区域
                from ..translation_splitter import parse_top_bottom
                for group, translation, group_idx, meta, skip_ids in zip(
                    groups_to_translate,
                    translations,
                    group_indexes,
                    crosspage_meta,
                    skip_region_ids_list,
                ):
                    crosspage_region = meta["region"] if meta else None
                    crosspage_extra = meta["extra"] if meta else ""

                    if crosspage_region and getattr(self, "_carryover_store", None):
                        parse_error = None
                        try:
                            top_text, bottom_text = parse_top_bottom(translation)
                        except Exception as exc:
                            parse_error = str(exc)
                            top_text, bottom_text = translation, ""
                        parsed_bottom = bottom_text
                        fallback_used = False
                        fallback_mode = None
                        if not bottom_text and crosspage_extra:
                            if ai_translator:
                                translated_extra = await ai_translator.translate_batch(
                                    [crosspage_extra]
                                )
                                candidate = (
                                    (translated_extra[0] if translated_extra else "") or ""
                                ).strip()
                                if candidate:
                                    if (self.target_lang or "").startswith("zh") and _has_hangul(candidate):
                                        bottom_text = ""
                                        fallback_mode = "retranslate_failed_lang"
                                    elif candidate == crosspage_extra.strip():
                                        bottom_text = ""
                                        fallback_mode = "retranslate_failed_same"
                                    else:
                                        bottom_text = candidate
                                        fallback_used = True
                                        fallback_mode = "retranslate"
                            if not bottom_text and not ai_translator:
                                bottom_text = crosspage_extra
                                fallback_used = True
                                fallback_mode = "raw"
                        if getattr(context, "crosspage_debug", None) is None:
                            context.crosspage_debug = {}
                        context.crosspage_debug.setdefault("translations", []).append(
                            {
                                "pair_id": crosspage_region.crosspage_pair_id,
                                "raw_output": translation,
                                "parsed_top": top_text,
                                "parsed_bottom": parsed_bottom,
                                "fallback_used": fallback_used,
                                "fallback_mode": fallback_mode,
                                "fallback_bottom": bottom_text if fallback_used else None,
                                "parse_error": parse_error,
                                "source_text": crosspage_region.source_text,
                                "crosspage_texts": crosspage_extra,
                            }
                        )
                        crosspage_region.target_text = top_text
                        if bottom_text:
                            self._carryover_store.put(
                                pair_id=crosspage_region.crosspage_pair_id,
                                bottom_text=bottom_text,
                                from_page=context.image_path,
                                to_page="next",
                            )
                        if debug:
                            logger.info(
                                "[%s] assign group[%d] crosspage -> %s",
                                context.task_id,
                                group_idx,
                                translation,
                            )
                        continue
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
                        non_skip = [r for r in group if r.region_id not in skip_ids]
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
                                if getattr(region, "skip_translation", False):
                                    region.target_text = ""
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
                        if logger.isEnabledFor(logging.DEBUG):
                            group_src = " ".join(
                                (r.source_text or "").strip()
                                for r in group
                                if r.source_text
                            )
                            logger.debug(
                                f"[{context.task_id}] 分组翻译: src='{_snippet(group_src)}' "
                                f"tgt='{_snippet(translation)}'"
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

        try:
            writer = DebugArtifactWriter()
            writer.write_grouping(context, context.image_path)
            writer.write_translation(context, context.image_path)
        except Exception as exc:
            logger.debug(f"[{context.task_id}] Debug artifacts (Translator) skipped: {exc}")

        return context
