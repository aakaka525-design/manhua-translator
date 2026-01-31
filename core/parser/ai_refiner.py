from __future__ import annotations

import json
import os
from typing import Any

from core.parser.utils import is_missing, merge_warnings


FIELDS = (
    "title",
    "author",
    "date",
    "summary",
    "cover",
    "content_text",
    "paragraphs",
)


def ai_refine(parsed: dict, snippet: str) -> dict:
    base = dict(parsed or {})
    warnings: list[str] = []
    filled_from_ai: set[str] = set()

    missing_fields = [field for field in FIELDS if is_missing(base.get(field))]
    low_conf_fields = _low_confidence_fields(base, threshold=0.55)
    ai_payload: dict[str, Any] = {}

    ai_fields = list(dict.fromkeys([*missing_fields, *low_conf_fields]))
    if ai_fields and snippet and _has_ai_config():
        try:
            ai_payload = _call_ai(snippet, ai_fields)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"AI refine failed: {exc}")
            ai_payload = {}

    for field in ai_fields:
        if field in ai_payload:
            value = _normalize_field(field, ai_payload.get(field))
            if not is_missing(value):
                if field in low_conf_fields or is_missing(base.get(field)):
                    base[field] = value
                    filled_from_ai.add(field)

    confidence, source_map = _build_metadata(base, filled_from_ai)
    base["confidence"] = confidence
    base["source_map"] = source_map
    if warnings:
        base["warnings"] = merge_warnings(base.get("warnings"), warnings)
    return base


def _build_metadata(parsed: dict, filled_from_ai: set[str]) -> tuple[dict, dict]:
    confidence: dict[str, float] = {}
    source_map: dict[str, str] = {}
    for field in FIELDS:
        value = parsed.get(field)
        if field in filled_from_ai:
            source_map[field] = "ai"
            confidence[field] = 0.7
        elif is_missing(value):
            source_map[field] = "missing"
            confidence[field] = 0.0
        else:
            source_map[field] = "rule"
            confidence[field] = 0.6
    return confidence, source_map


def _low_confidence_fields(parsed: dict, threshold: float) -> list[str]:
    confidence = parsed.get("confidence")
    if not isinstance(confidence, dict):
        return []
    return [
        field
        for field in FIELDS
        if field in confidence and confidence.get(field, 1.0) < threshold
    ]


def _normalize_field(field: str, value: Any) -> Any:
    if field == "paragraphs":
        if isinstance(value, str):
            return _split_paragraphs(value)
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return None
    if isinstance(value, str):
        trimmed = value.strip()
        return trimmed or None
    return value


def _split_paragraphs(text: str) -> list[str]:
    chunks = [chunk.strip() for chunk in text.split("\n\n") if chunk.strip()]
    if chunks:
        return chunks
    return [line.strip() for line in text.splitlines() if line.strip()]


def _has_ai_config() -> bool:
    return bool(os.getenv("PPIO_API_KEY") or os.getenv("OPENAI_API_KEY"))


def _call_ai(snippet: str, missing_fields: list[str]) -> dict[str, Any]:
    api_key = os.getenv("PPIO_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("PPIO_BASE_URL")
    model = os.getenv("PPIO_MODEL", "glm-4-flash-250414")
    if not api_key:
        return {}

    try:
        from openai import OpenAI
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("OpenAI client not available") from exc

    client = OpenAI(base_url=base_url, api_key=api_key)
    wanted = ", ".join(missing_fields)
    prompt = (
        "Extract article fields from the HTML/text snippet. "
        "Return a JSON object with only these keys: "
        f"{wanted}. Use null when unknown. "
        "paragraphs must be a list of strings. Output JSON only.\n\n"
        f"Snippet:\n{snippet}"
    )
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=800,
        temperature=0.2,
        stream=False,
    )
    message = response.choices[0].message
    text = message.content if message is not None else ""
    content = (text or "").strip()
    return _parse_json_object(content)


def _parse_json_object(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("AI response is not valid JSON")
        parsed = json.loads(content[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("AI response JSON is not an object")
    return parsed
