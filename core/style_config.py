from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import yaml


@dataclass(frozen=True)
class StyleConfig:
    font_size_ref_range: Tuple[float, float] = (0.85, 1.15)
    font_size_fallback: Tuple[int, int] = (16, 32)
    font_size_relax_min: int = 12


def _coerce_tuple(value, size, cast):
    if not isinstance(value, (list, tuple)) or len(value) != size:
        return None
    return tuple(cast(v) for v in value)


def load_style_config(path: Optional[Path] = None) -> StyleConfig:
    if path is None:
        path = Path(__file__).resolve().parents[1] / "config" / "style.yml"
    if not path.exists():
        return StyleConfig()
    data = yaml.safe_load(path.read_text()) or {}
    ref_range = _coerce_tuple(data.get("font_size_ref_range"), 2, float)
    fallback = _coerce_tuple(data.get("font_size_fallback"), 2, int)
    relax_min = data.get("font_size_relax_min")
    return StyleConfig(
        font_size_ref_range=ref_range or (0.85, 1.15),
        font_size_fallback=fallback or (16, 32),
        font_size_relax_min=int(relax_min) if relax_min is not None else 12,
    )
