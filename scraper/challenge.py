from __future__ import annotations

CLOUDFLARE_MARKERS = (
    "cf-browser-verification",
    "challenge-platform",
    "cloudflare ray id",
    "attention required",
    "just a moment",
)


def looks_like_challenge(html: str) -> bool:
    if not html:
        return False
    content = html.lower()
    return any(marker in content for marker in CLOUDFLARE_MARKERS)
