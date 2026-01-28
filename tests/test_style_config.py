from pathlib import Path

from core.style_config import load_style_config


def test_style_config_defaults(tmp_path: Path):
    cfg = load_style_config(path=tmp_path / "missing.yml")
    assert cfg.font_size_ref_range == (0.85, 1.15)
    assert cfg.font_size_fallback == (16, 32)
    assert cfg.font_size_relax_min == 12
    assert cfg.font_size_estimate_bias == 1.0
    assert cfg.line_spacing_default == 1.2
    assert cfg.line_spacing_compact == 1.1
    assert cfg.line_spacing_compact_threshold == 0.9


def test_style_config_overrides(tmp_path: Path):
    path = tmp_path / "style.yml"
    path.write_text(
        "font_size_ref_range: [0.8, 1.2]\n"
        "font_size_fallback: [14, 30]\n"
        "font_size_relax_min: 10\n"
        "font_size_estimate_bias: 1.12\n"
        "line_spacing_default: 1.25\n"
        "line_spacing_compact: 1.05\n"
        "line_spacing_compact_threshold: 0.85\n"
    )
    cfg = load_style_config(path=path)
    assert cfg.font_size_ref_range == (0.8, 1.2)
    assert cfg.font_size_fallback == (14, 30)
    assert cfg.font_size_relax_min == 10
    assert cfg.font_size_estimate_bias == 1.12
    assert cfg.line_spacing_default == 1.25
    assert cfg.line_spacing_compact == 1.05
    assert cfg.line_spacing_compact_threshold == 0.85
