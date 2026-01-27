import re
from typing import List

from .models import RegionData
from .modules.translator import _is_sfx as _is_sfx_translator


class OCRPostProcessor:
    _WS_RE = re.compile(r"\s+")
    _KO_FIXES = [
        (re.compile(r"이닌"), "이번"),
        (re.compile(r"억은"), "역은"),
    ]
    _SFX_CJK_RE = re.compile(r"^[\u4e00-\u9fff]{1,6}[!！]?$")
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
