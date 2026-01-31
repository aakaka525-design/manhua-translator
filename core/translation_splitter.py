import json


def parse_top_bottom(text: str):
    data = json.loads(text)
    top = data.get("top", "").strip()
    bottom = data.get("bottom", "").strip()
    return top, bottom
