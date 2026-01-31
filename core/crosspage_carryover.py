import json
import time
from pathlib import Path


class CrosspageCarryOverStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._data = {}

    def put(self, pair_id: str, bottom_text: str, from_page: str, to_page: str):
        self._data[pair_id] = {
            "pair_id": pair_id,
            "bottom_text": bottom_text,
            "from_page": from_page,
            "to_page": to_page,
            "created_at": time.time(),
            "status": "pending",
        }

    def get(self, pair_id: str):
        item = self._data.get(pair_id)
        return item["bottom_text"] if item else None

    def consume(self, pair_id: str):
        item = self._data.pop(pair_id, None)
        if not item:
            return None
        return item["bottom_text"]

    def flush(self):
        if not self._data:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            for item in self._data.values():
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
