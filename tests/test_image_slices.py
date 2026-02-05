import pytest
from core.image_io import compute_webp_slices


@pytest.mark.parametrize("height,expected_slices", [
    (16383, 1),
    (16384, 2),
    (32000, 2),
    (62012, 4),
])
def test_slice_count(height, expected_slices):
    slices = compute_webp_slices(height, slice_height=16000, overlap=32)
    assert len(slices) == expected_slices


def test_slice_positions():
    slices = compute_webp_slices(62012, slice_height=16000, overlap=32)
    assert slices[0] == (0, 16000)
    assert slices[1][0] == 15968
    assert slices[-1][1] == 62012
