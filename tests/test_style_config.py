from pathlib import Path

from core.style_config import load_style_config


def test_style_config_defaults(tmp_path: Path):
    cfg = load_style_config(path=tmp_path / "missing.yml")
    assert cfg.font_size_ref_range == (0.85, 1.15)
    assert cfg.font_size_fallback == (16, 32)
    assert cfg.font_size_relax_min == 12


def test_style_config_overrides(tmp_path: Path):
    path = tmp_path / "style.yml"
    path.write_text(
        "font_size_ref_range: [0.8, 1.2]\n"
        "font_size_fallback: [14, 30]\n"
        "font_size_relax_min: 10\n"
    )
    cfg = load_style_config(path=path)
    assert cfg.font_size_ref_range == (0.8, 1.2)
    assert cfg.font_size_fallback == (14, 30)
    assert cfg.font_size_relax_min == 10
