from __future__ import annotations

import asyncio

import pytest

from app.routes import translate as translate_routes


@pytest.mark.asyncio
async def test_broadcast_event_drops_oldest_when_listener_queue_is_full():
    queue = asyncio.Queue(maxsize=1)
    translate_routes._listeners.add(queue)
    try:
        await translate_routes.broadcast_event({"n": 1})
        # If broadcast uses blocking `await queue.put(...)`, this will deadlock when
        # a slow client doesn't drain the SSE queue.
        await asyncio.wait_for(translate_routes.broadcast_event({"n": 2}), timeout=0.2)

        # Queue should stay bounded and keep the latest event.
        assert queue.qsize() == 1
        payload = await queue.get()
        assert '"n": 2' in payload
    finally:
        translate_routes._listeners.discard(queue)
