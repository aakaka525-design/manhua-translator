import pytest

from scripts.upscale_eval import compute_stats, gain_ratio


def test_compute_stats_empty():
    stats = compute_stats([])
    assert stats["avg"] == 0.0
    assert stats["median"] == 0.0
    assert stats["count"] == 0


def test_gain_ratio():
    assert gain_ratio(0.5, 0.6) == pytest.approx(0.2)
