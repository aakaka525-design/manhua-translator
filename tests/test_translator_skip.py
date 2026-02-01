from core.modules.translator import _should_skip_translation


def test_skip_translation_roman_numeral():
    should_skip, reason = _should_skip_translation("Ⅲ")
    assert should_skip is True
    assert reason
