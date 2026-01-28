from core.models import RegionData


def test_region_font_size_metadata_defaults():
    region = RegionData()
    assert region.font_size_ref is None
    assert region.font_size_used is None
    assert region.font_size_relaxed is False
    assert region.font_size_source is None
