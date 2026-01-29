from pathlib import Path


def test_frontend_index_has_no_external_css():
    content = Path("frontend/index.html").read_text(encoding="utf-8")
    assert "fonts.googleapis.com" not in content
    assert "cdnjs.cloudflare.com" not in content


def test_frontend_entry_imports_local_fonts_and_icons():
    content = Path("frontend/src/main.js").read_text(encoding="utf-8")
    assert "@fontsource/bangers" in content
    assert "@fontsource/bebas-neue" in content
    assert "@fontsource/inter" in content
    assert "@fontsource/space-grotesk" in content
    assert "@fortawesome/fontawesome-free/css/all.css" in content
