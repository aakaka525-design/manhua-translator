from __future__ import annotations

PUNCTUATION = ["。", "！", "？", "…", "；", "，"]


def split_by_punctuation(text: str) -> tuple[str, str]:
    text = (text or "").strip()
    if not text:
        return "", ""
    if len(text) <= 4:
        mid = len(text) // 2
        return text[:mid], text[mid:]

    mid = len(text) // 2
    candidates = [i for i, ch in enumerate(text) if ch in PUNCTUATION]
    if candidates:
        best = min(candidates, key=lambda i: abs(i - mid))
        top = text[: best + 1]
        bottom = text[best + 1 :]
        if len(top.strip()) >= 2 and len(bottom.strip()) >= 2:
            return top.strip(), bottom.strip()

    split = int(len(text) * 0.5)
    top = text[:split]
    bottom = text[split:]
    return top.strip(), bottom.strip()
