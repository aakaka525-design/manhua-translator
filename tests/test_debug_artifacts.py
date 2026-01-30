from pathlib import Path

from PIL import Image

from core.models import Box2D, RegionData, TaskContext


def test_debug_writer_outputs_ocr_boxes(tmp_path: Path):
    img_path = tmp_path / "blank.png"
    Image.new("RGB", (200, 100), "white").save(img_path)

    ctx = TaskContext(image_path=str(img_path))
    ctx.regions = [
        RegionData(
            box_2d=Box2D(x1=10, y1=10, x2=80, y2=40),
            source_text="HELLO",
            normalized_text="Hello",
            confidence=0.9,
        )
    ]

    from core.debug_artifacts import DebugArtifactWriter

    writer = DebugArtifactWriter(output_dir=tmp_path, enabled=True)
    output = writer.write_ocr(ctx, image_path=str(img_path))

    assert output.exists()


def test_debug_writer_outputs_translation_boxes(tmp_path: Path):
    img_path = tmp_path / "blank.png"
    Image.new("RGB", (200, 100), "white").save(img_path)

    ctx = TaskContext(image_path=str(img_path))
    ctx.regions = [
        RegionData(
            box_2d=Box2D(x1=10, y1=10, x2=80, y2=40),
            target_text="你好",
        )
    ]

    from core.debug_artifacts import DebugArtifactWriter

    writer = DebugArtifactWriter(output_dir=tmp_path, enabled=True)
    out_path = writer.write_translation(ctx, image_path=str(img_path))

    assert out_path.exists()


def test_debug_writer_disabled_no_output(tmp_path: Path):
    from core.debug_artifacts import DebugArtifactWriter

    writer = DebugArtifactWriter(output_dir=tmp_path, enabled=False)
    assert writer.write_ocr(TaskContext(image_path="x"), "x") is None
