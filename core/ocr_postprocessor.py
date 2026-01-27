import re
from typing import List

from .models import RegionData


class OCRPostProcessor:
    _WS_RE = re.compile(r"\s+")
    _KO_FIXES = [
        (re.compile(r"이닌"), "이번"),
        (re.compile(r"억은"), "역은"),
    ]

    def _normalize(self, text: str) -> str:
        if not text:
            return ""
        return self._WS_RE.sub(" ", text).strip()

    def _is_sfx(self, text: str) -> bool:
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
