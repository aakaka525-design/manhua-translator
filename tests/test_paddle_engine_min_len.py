import numpy as np

from core.vision.ocr.paddle_engine import PaddleOCREngine


class _DummyOCR:
    def predict(self, chunk):
        return [
            {
                "rec_texts": ["너"],
                "rec_scores": [0.9],
                "rec_boxes": [[0, 0, 10, 10]],
            }
        ]


def test_paddle_engine_allows_single_char_korean():
    engine = PaddleOCREngine(lang="korean")
    chunk = np.zeros((12, 12, 3), dtype=np.uint8)

    regions = engine._process_chunk(
        _DummyOCR(),
        chunk,
        0,
        min_score=0.1,
        min_len=engine._min_len_for_lang(),
    )

    assert len(regions) == 1
    assert regions[0].source_text == "너"
