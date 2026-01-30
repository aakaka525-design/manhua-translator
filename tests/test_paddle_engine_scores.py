import numpy as np

from core.vision.ocr.paddle_engine import PaddleOCREngine


class _FakeOCR:
    def predict(self, _chunk):
        return [
            {
                "rec_texts": ["Hi"],
                "rec_scores": [(0.9, 0.1)],
                "rec_boxes": [[0, 0, 5, 5]],
            }
        ]


def test_process_chunk_accepts_tuple_scores():
    engine = PaddleOCREngine(lang="en")
    chunk = np.zeros((10, 10, 3), dtype=np.uint8)

    regions = engine._process_chunk(_FakeOCR(), chunk, 0, min_len=2)

    assert len(regions) == 1
    assert regions[0].source_text == "Hi"
    assert regions[0].confidence == 0.9
