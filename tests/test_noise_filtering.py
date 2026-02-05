from core.vision.ocr.postprocessing import filter_noise_regions
from core.models import RegionData, Box2D


def _region(text: str, conf: float = 0.95) -> RegionData:
    return RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=120, y2=40),
        source_text=text,
        confidence=conf,
    )


def test_noise_filtering_samples():
    dialogue = _region("Hello there")
    sfx = _region("砰")
    watermark = _region("example.com")
    chapter = _region("第12话")
    alnum_short = _region("A12")

    regions = [dialogue, sfx, watermark, chapter, alnum_short]
    out = filter_noise_regions(regions, image_height=1000)

    assert dialogue in out
    assert sfx in out
    assert chapter in out
    assert watermark not in out
    assert alnum_short not in out
