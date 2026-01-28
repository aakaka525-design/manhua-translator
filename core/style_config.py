from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import yaml


@dataclass(frozen=True)
class StyleConfig:
    font_size_ref_range: Tuple[float, float] = (0.85, 1.15)
    font_size_fallback: Tuple[int, int] = (16, 32)
    font_size_relax_min: int = 12
    font_size_estimate_bias: float = 1.0
    line_spacing_default: float = 1.2
    line_spacing_compact: float = 1.1
    line_spacing_compact_threshold: float = 0.9


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
    bias = data.get("font_size_estimate_bias")
    line_spacing_default = data.get("line_spacing_default")
    line_spacing_compact = data.get("line_spacing_compact")
    line_spacing_compact_threshold = data.get("line_spacing_compact_threshold")
    return StyleConfig(
        font_size_ref_range=ref_range or (0.85, 1.15),
        font_size_fallback=fallback or (16, 32),
        font_size_relax_min=int(relax_min) if relax_min is not None else 12,
        font_size_estimate_bias=float(bias) if bias is not None else 1.0,
        line_spacing_default=float(line_spacing_default) if line_spacing_default is not None else 1.2,
        line_spacing_compact=float(line_spacing_compact) if line_spacing_compact is not None else 1.1,
        line_spacing_compact_threshold=float(line_spacing_compact_threshold) if line_spacing_compact_threshold is not None else 0.9,
    )
