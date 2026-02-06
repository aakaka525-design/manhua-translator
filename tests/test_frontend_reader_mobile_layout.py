from pathlib import Path


def test_reader_content_has_top_offset_for_fixed_toolbar():
    content = Path("frontend/src/views/ReaderView.vue").read_text(encoding="utf-8")
    assert "pt-14" in content
    assert "sm:pt-16" in content
