import numpy as np


def test_detect_and_recognize_can_disable_edge_tiles(monkeypatch):
    monkeypatch.setenv("OCR_EDGE_TILE_ENABLE", "0")

    from core.vision.ocr.paddle_engine import PaddleOCREngine

    engine = PaddleOCREngine(lang="en")
    monkeypatch.setattr(engine, "_init_ocr", lambda: object())

    calls = {"chunks": 0}

    def _fake_process_chunk(*_args, **_kwargs):
        calls["chunks"] += 1
        return []

    monkeypatch.setattr(engine, "_process_chunk", _fake_process_chunk)

    class _FakeTilingManager:
        def should_tile(self, _height):
            return True

        def create_tiles(self, image):
            return [
                type(
                    "Tile",
                    (),
                    {
                        "image": image,
                        "x_offset": 0,
                        "y_offset": 0,
                        "height": image.shape[0],
                        "width": image.shape[1],
                        "index": 0,
                    },
                )()
            ]

        def create_edge_tiles(self, _image):
            raise AssertionError("edge tiles should be disabled")

        def remap_regions(self, regions, _tile):
            return regions

        def merge_regions(self, regions, iou_threshold=0.5):
            return regions

    monkeypatch.setattr(
        "core.vision.ocr.paddle_engine.get_tiling_manager",
        lambda: _FakeTilingManager(),
    )
    monkeypatch.setattr(
        "core.vision.ocr.paddle_engine.cv2.imread",
        lambda _path: np.zeros((3000, 200, 3), dtype=np.uint8),
    )

    regions = engine._detect_and_recognize_sync("dummy.jpg")
    assert regions == []
    assert calls["chunks"] == 1
