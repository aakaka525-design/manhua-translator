from pathlib import Path


def test_scraper_gui_moved_to_tools():
    assert Path("tools/scraper_gui.py").exists()
    assert not Path("scripts/scraper_gui.py").exists()
