import re

# Korean SFX -> Chinese onomatopoeia
KO_SFX_MAP = {
    "팅": "叮",
    "딱": "咔",
    "팡": "砰",
    "펑": "嘭",
    "탕": "砰",
    "쿵": "咚",
    "쾅": "轰",
    "퍽": "噗",
    "헉": "哈",
    "윽": "呃",
    "흑": "呜",
    "으악": "啊啊",
    "후": "呼",
    "휴": "呼",
    "휙": "嗖",
    "슥": "唰",
    "슥슥": "唰唰",
    "쓱": "唰",
    "쓱쓱": "唰唰",
    "파닥": "扑腾",
    "파닥파닥": "扑腾扑腾",
    "두근두근": "怦怦",
    "덜컹덜컹": "哐当哐当",
    "철컹철컹": "铛啷铛啷",
    "우두둑": "噼啪",
    "잘근": "嚼嚼",
    "토톡": "哒哒",
    "독토톡도": "哒哒哒",
    "떠링": "叮",
}

# English SFX -> Chinese
EN_SFX_MAP = {
    "BANG": "砰",
    "BOOM": "轰",
    "CRASH": "哗啦",
    "SLASH": "刷",
    "WHOOSH": "嗖",
    "THUD": "砰",
    "THUMP": "咚",
    "CRACK": "咔嚓",
    "RUMBLE": "隆隆",
    "SPLASH": "哗",
    "CLICK": "咔哒",
    "CLACK": "咔",
    "TAP": "嗒",
    "RUSTLE": "沙沙",
    "RATTLE": "喀啦",
}

_HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")
_TRAIL_PUNCT_RE = re.compile(r"([!！?？….,。]+)$")


def _split_trailing_punct(text: str) -> tuple[str, str]:
    if not text:
        return "", ""
    match = _TRAIL_PUNCT_RE.search(text)
    if not match:
        return text, ""
    return text[: match.start()], match.group(1)


def _romanize_hangul(text: str) -> str:
    # Revised Romanization
    L = [
        "g", "kk", "n", "d", "tt", "r", "m", "b", "pp", "s", "ss", "ng",
        "j", "jj", "ch", "k", "t", "p", "h"
    ]
    V = [
        "a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa", "wae",
        "oe", "yo", "u", "wo", "we", "wi", "yu", "eu", "ui", "i"
    ]
    T = [
        "", "k", "k", "ks", "n", "nj", "nh", "t", "l", "lk", "lm", "lb",
        "ls", "lt", "lp", "lh", "m", "p", "ps", "t", "t", "ng", "t",
        "t", "k", "t", "p", "t"
    ]

    out = []
    for ch in text:
        code = ord(ch)
        if 0xAC00 <= code <= 0xD7A3:
            idx = code - 0xAC00
            l = idx // 588
            v = (idx % 588) // 28
            t = idx % 28
            out.append(L[l] + V[v] + T[t])
        else:
            out.append(ch)
    return "".join(out)


def translate_sfx(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    base, suffix = _split_trailing_punct(raw)
    key = base.strip()
    if not key:
        return raw

    upper_key = key.upper()
    if upper_key in EN_SFX_MAP:
        return EN_SFX_MAP[upper_key] + suffix
    if key in KO_SFX_MAP:
        return KO_SFX_MAP[key] + suffix
    if _HANGUL_RE.search(key):
        return _romanize_hangul(key) + suffix
    return key + suffix
