import re
from typing import List

from .models import RegionData
from .modules.translator import _is_sfx as _is_sfx_translator


class OCRPostProcessor:
    _WS_RE = re.compile(r"\s+")
    
    # 韩文 OCR 常见误识别纠正规则
    _KO_FIXES = [
        (re.compile(r"이닌"), "이번"),
        (re.compile(r"억은"), "역은"),
        (re.compile(r"닌역"), "번역"),
        (re.compile(r"이아"), "이야"),
        (re.compile(r"운요"), "은요"),
    ]
    
    # 中文拟声词白名单（更精准，避免误判普通短语）
    _SFX_CN_WORDS = {"砰", "咔", "咔嚓", "嗖", "嘭", "哗", "呼", "啪", "嘎", "轰", "嘶", "咚", "叮", "嗡", "嘀", "哐", "咣", "嘣", "噗", "咻", "唰"}
    _SFX_CJK_RE = re.compile(r"^(砰|咔嚓|咔|嗖|嘭|哗|呼|啪|嘎|轰|嘶|咚|叮|嗡|嘀|哐|咣|嘣|噗|咻|唰)+[！!]*$")
    _SFX_JP_RE = re.compile(r"^[\u3040-\u30ff]{2,8}[!！]?$")
    _SFX_KO_RE = re.compile(r"^[\uac00-\ud7a3]{1,6}[!！]?$")

    def _normalize(self, text: str) -> str:
        if not text:
            return ""
        return self._WS_RE.sub(" ", text).strip()

    def _is_sfx(self, text: str) -> bool:
        if not text:
            return False
        if _is_sfx_translator(text):
            return True
        t = text.strip()
        if self._SFX_CJK_RE.match(t):
            return True
        if self._SFX_JP_RE.match(t):
            return True
        if self._SFX_KO_RE.match(t):
            return True
        return False

    def _fix_korean(self, text: str) -> str:
        out = text
        for pattern, repl in self._KO_FIXES:
            out = pattern.sub(repl, out)
        return out

    def process_regions(self, regions: List[RegionData], lang: str = "en") -> List[RegionData]:
        for r in regions:
            if r.source_text:
                normalized = self._normalize(r.source_text)
                if lang in {"korean", "ko"}:
                    normalized = self._fix_korean(normalized)
                r.normalized_text = normalized
                r.is_sfx = self._is_sfx(r.normalized_text)
            else:
                r.normalized_text = ""
                r.is_sfx = False
        return regions
