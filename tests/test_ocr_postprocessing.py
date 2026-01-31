from core.models import Box2D, RegionData
from core.vision.ocr.postprocessing import filter_noise_regions, geometric_cluster_dedup


def test_filter_noise_regions_keeps_domain_when_relaxed():
    region = RegionData(
        box_2d=Box2D(x1=10, y1=10, x2=200, y2=30),
        source_text="NEWTOKI.COM",
        confidence=0.9,
    )

    filtered = filter_noise_regions([region], image_height=2000, relaxed=True)

    assert len(filtered) == 1
    assert filtered[0].source_text == "NEWTOKI.COM"


def test_geometric_cluster_dedup_merges_overlapping_texts():
    r1 = RegionData(
        box_2d=Box2D(x1=10, y1=10, x2=60, y2=30),
        source_text="그동안",
        confidence=0.9,
    )
    r2 = RegionData(
        box_2d=Box2D(x1=55, y1=12, x2=120, y2=32),
        source_text="일방적으로",
        confidence=0.9,
    )

    merged = geometric_cluster_dedup([r1, r2])

    assert len(merged) == 1
    assert "그동안" in merged[0].source_text
    assert "일방적으로" in merged[0].source_text
