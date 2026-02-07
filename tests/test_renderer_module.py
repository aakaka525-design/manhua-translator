import asyncio
from pathlib import Path

from PIL import Image

from core.models import TaskContext
from core.modules.renderer import RendererModule


def test_renderer_uses_intermediate_output_when_upscale_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("OUTPUT_FORMAT", "webp")
    monkeypatch.setenv("UPSCALE_ENABLE", "1")

    source = tmp_path / "input.png"
    Image.new("RGB", (32, 17000), "white").save(source)

    ctx = TaskContext(
        image_path=str(source),
        output_path=str(tmp_path / "out.webp"),
        regions=[],
    )
    module = RendererModule(output_dir=str(tmp_path))

    asyncio.run(module.process(ctx))

    assert not str(ctx.output_path).endswith("_slices.json")
    assert Path(ctx.output_path).exists()
