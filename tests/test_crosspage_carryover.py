import json
from pathlib import Path

from core.crosspage_carryover import CrosspageCarryOverStore


def test_carryover_store_persist_and_consume(tmp_path):
    store_path = tmp_path / "_carryover.jsonl"
    store = CrosspageCarryOverStore(store_path)

    store.put(pair_id="p1", bottom_text="B", from_page="3.jpg", to_page="4.jpg")
    assert store.get("p1") == "B"

    # Persist to disk
    store.flush()
    data = [json.loads(line) for line in store_path.read_text().splitlines()]
    assert data[0]["pair_id"] == "p1"
    assert data[0]["bottom_text"] == "B"

    # Consume clears entry
    assert store.consume("p1") == "B"
    assert store.get("p1") is None
