import numpy as np

from core.vision.tiling import TilingManager


def test_tiling_manager_applies_edge_padding():
    manager = TilingManager(tile_height=100, overlap_ratio=0.5, min_tile_height=20, edge_padding=10)
    image = np.zeros((230, 50, 3), dtype=np.uint8)

    tiles = manager.create_tiles(image)

    # stride = 100 - 50 = 50, expected y_start = max(0, y - pad)
    expected_offsets = [0, 40, 90, 140]
    assert [t.y_offset for t in tiles] == expected_offsets

    expected_heights = [110, 120, 120, 90]
    assert [t.height for t in tiles] == expected_heights


def test_tiling_manager_creates_edge_tiles():
    manager = TilingManager(
        tile_height=100,
        overlap_ratio=0.5,
        min_tile_height=20,
        edge_padding=10,
        edge_band_ratio=0.2,
        edge_band_min_height=30,
    )
    image = np.zeros((230, 50, 3), dtype=np.uint8)

    tiles = manager.create_edge_tiles(image)

    assert len(tiles) == 2
    assert [t.y_offset for t in tiles] == [0, 174]
    assert [t.height for t in tiles] == [56, 56]
