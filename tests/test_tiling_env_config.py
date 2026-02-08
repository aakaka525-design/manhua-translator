def test_get_tiling_manager_reads_env_and_clamps(monkeypatch):
    import core.vision.tiling as tiling

    # Ensure a clean singleton between tests.
    monkeypatch.setattr(tiling, "_tiling_manager", None)
    monkeypatch.setattr(tiling, "_tiling_manager_sig", None)

    monkeypatch.setenv("OCR_TILE_HEIGHT", "1000")
    monkeypatch.setenv("OCR_TILE_OVERLAP_RATIO", "0.9")  # should clamp to 0.5
    monkeypatch.setenv("OCR_EDGE_BAND_RATIO", "0.9")  # should clamp to 0.5

    mgr = tiling.get_tiling_manager()
    assert mgr.tile_height == 1000
    assert mgr.overlap_ratio == 0.5
    assert mgr.overlap_pixels == 500
    assert mgr.edge_band_ratio == 0.5

    # Changing env should rebuild the manager.
    monkeypatch.setenv("OCR_TILE_HEIGHT", "900")
    mgr2 = tiling.get_tiling_manager()
    assert mgr2.tile_height == 900
