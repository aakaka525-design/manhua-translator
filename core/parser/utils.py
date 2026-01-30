from __future__ import annotations

from typing import Any


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, list):
        return len(value) == 0
    return False


def merge_warnings(existing: Any, new_items: list[str]) -> list[str]:
    merged: list[str] = []
    if isinstance(existing, list):
        merged.extend(str(item) for item in existing if str(item))
    merged.extend(new_items)
    return merged
