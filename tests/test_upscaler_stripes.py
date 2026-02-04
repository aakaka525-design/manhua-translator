import numpy as np
import pytest

from core.modules import upscaler


def test_compute_stripes_returns_full_when_below_threshold():
    stripes = upscaler.compute_stripes(height=1000, threshold=4000, stripe_height=2000, overlap=64)
    assert stripes == [(0, 1000)]


def test_compute_stripes_merges_small_tail():
    # height=3986 with stripe=2000, overlap=64 leaves tail < overlap
    stripes = upscaler.compute_stripes(height=3986, threshold=3900, stripe_height=2000, overlap=64)
    assert stripes[-1][1] == 3986
    # ensure only 2 stripes, tail merged
    assert len(stripes) == 2


def test_compute_stripes_rejects_bad_config():
    with pytest.raises(ValueError):
        upscaler.compute_stripes(height=5000, threshold=4000, stripe_height=64, overlap=64)


def test_crop_and_merge_preserves_total_height():
    # three stripes with overlap 2 at scale 2 => overlap_px=4
    stripes = [
        np.zeros((10, 4, 3), dtype=np.uint8),
        np.zeros((10, 4, 3), dtype=np.uint8),
        np.zeros((10, 4, 3), dtype=np.uint8),
    ]
    merged = upscaler.crop_and_merge(stripes, overlap_px=4, scale=2)
    # first keeps 6, middle keeps 2, last keeps 6 => 14 total
    assert merged.shape[0] == 14
