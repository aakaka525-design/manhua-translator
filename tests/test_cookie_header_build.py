import json
from pathlib import Path

from app.routes.scraper import _build_cookie_header


def test_build_cookie_header_uses_storage_state(tmp_path):
    state = {
        "cookies": [
            {"name": "a", "value": "b"},
            {"name": "a", "value": "c"},
        ]
    }
    path = tmp_path / "state.json"
    path.write_text(json.dumps(state), encoding="utf-8")

    header = _build_cookie_header(str(path), "")
    assert header == "a=c"
