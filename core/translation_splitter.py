import json
import re


def parse_top_bottom(text: str):
    raw = (text or "").strip()
    data = None
    try:
        data = json.loads(raw)
    except Exception:
        data = None

    if isinstance(data, dict):
        top = str(data.get("top", "") or "").strip()
        bottom = str(data.get("bottom", "") or "").strip()
        return top, bottom

    top = _extract_json_string_field(raw, "top")
    bottom = _extract_json_string_field(raw, "bottom")
    if top is None and bottom is None:
        # Keep old behavior for completely non-JSON text.
        raise ValueError("Invalid top/bottom JSON payload")
    return (top or "").strip(), (bottom or "").strip()


def _extract_json_string_field(raw: str, key: str):
    match = re.search(rf'"{re.escape(key)}"\s*:\s*"', raw)
    if not match:
        return None
    i = match.end()
    buf = []
    escaped = False
    while i < len(raw):
        ch = raw[i]
        if escaped:
            buf.append(ch)
            escaped = False
            i += 1
            continue
        if ch == "\\":
            escaped = True
            i += 1
            continue
        if ch == '"':
            break
        buf.append(ch)
        i += 1
    content = "".join(buf)
    # Reuse JSON unescaping rules for escaped unicode and quotes.
    try:
        return json.loads(f'"{content}"')
    except Exception:
        return content
