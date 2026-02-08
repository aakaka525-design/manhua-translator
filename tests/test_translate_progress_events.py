from __future__ import annotations

from uuid import uuid4

import pytest

from app.routes import translate as translate_routes
from core.models import TaskStatus


@pytest.mark.asyncio
async def test_pipeline_status_callback_includes_chapter_metadata(monkeypatch):
    events = []

    async def _fake_broadcast(payload: dict):
        events.append(payload)

    monkeypatch.setattr(translate_routes, "broadcast_event", _fake_broadcast)

    task_id = uuid4()
    translate_routes._task_meta[task_id] = {
        "manga_id": "demo",
        "chapter_id": "chapter-1",
        "image_name": "1.jpg",
    }

    try:
        await translate_routes.pipeline_status_callback(
            "translator", TaskStatus.PROCESSING, task_id
        )
    finally:
        translate_routes._task_meta.pop(task_id, None)

    assert events
    event = events[-1]
    assert event["type"] == "progress"
    assert event["manga_id"] == "demo"
    assert event["chapter_id"] == "chapter-1"
    assert event["image_name"] == "1.jpg"
    assert event["stage"] == "translator"
