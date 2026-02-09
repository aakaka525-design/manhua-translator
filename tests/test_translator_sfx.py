import asyncio

from core.models import Box2D, RegionData, TaskContext
from core.modules.translator import TranslatorModule, _is_sfx


def _run_translate(regions):
    ctx = TaskContext(image_path="/tmp/input.png")
    ctx.regions = regions
    module = TranslatorModule(source_lang="korean", target_lang="zh", use_mock=True, use_ai=False)
    return asyncio.run(module.process(ctx))


def test_translator_sfx_dictionary_translation():
    result = _run_translate(
        [
            RegionData(
                box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
                source_text="잘근",
                normalized_text="잘근",
                is_sfx=True,
                confidence=0.9,
            )
        ]
    )
    assert result.regions[0].target_text == "嚼嚼"


def test_translator_sfx_english_mapping():
    result = _run_translate(
        [
            RegionData(
                box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
                source_text="BANG!",
                normalized_text="BANG!",
                is_sfx=True,
                confidence=0.9,
            )
        ]
    )
    assert result.regions[0].target_text == "砰!"


def test_translator_sfx_unknown_korean_preserved():
    """Unknown Korean SFX should keep original art (do not render Hangul for zh targets)."""
    result = _run_translate(
        [
            RegionData(
                box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
                source_text="텅",
                normalized_text="텅",
                is_sfx=True,
                confidence=0.9,
            )
        ]
    )
    # Keep original (do not inpaint or render replacement text).
    assert (result.regions[0].target_text or "") == ""


def test_translator_sfx_cjk_and_jp_ko_rules():
    assert _is_sfx("砰")
    assert _is_sfx("カンッ")
    assert _is_sfx("쿵")
