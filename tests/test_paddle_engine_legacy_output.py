import numpy as np

from core.vision.ocr.paddle_engine import PaddleOCREngine


class _FakeLegacyOCR:
    def predict(self, chunk):  # pragma: no cover - force legacy path
        raise AttributeError("predict not supported")

    def ocr(self, chunk, det=True, rec=True, cls=False):
        # Mimic PaddleOCR legacy output: a list containing a list of detections.
        return [
            [
                (
                    [[0, 0], [10, 0], [10, 10], [0, 10]],
                    ("테스트1", 0.95),
                ),
                (
                    [[12, 0], [22, 0], [22, 10], [12, 10]],
                    ("테스트2", 0.90),
                ),
            ]
        ]


def test_process_chunk_handles_nested_legacy_output():
    engine = PaddleOCREngine(lang="korean")
    fake = _FakeLegacyOCR()
    chunk = np.zeros((32, 32, 3), dtype=np.uint8)

    regions = engine._process_chunk(fake, chunk, y_offset=0, min_score=0.5, min_len=1)

    assert [r.source_text for r in regions] == ["테스트1", "테스트2"]
