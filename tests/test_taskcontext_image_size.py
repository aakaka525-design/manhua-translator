import asyncio
from PIL import Image

from core.models import TaskContext
from core.modules.ocr import OCRModule


def test_ocr_sets_image_size(tmp_path):
    img = tmp_path / "img.png"
    Image.new("RGB", (123, 456)).save(img)
    ctx = TaskContext(image_path=str(img))
    module = OCRModule(use_mock=True)

    asyncio.run(module.process(ctx))

    assert ctx.image_width == 123
    assert ctx.image_height == 456
