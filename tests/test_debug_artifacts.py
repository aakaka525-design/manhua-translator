from pathlib import Path

from PIL import Image, ImageDraw

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


def test_debug_writer_outputs_mask_overlay(tmp_path: Path):
    img_path = tmp_path / "blank.png"
    mask_path = tmp_path / "mask.png"
    Image.new("RGB", (120, 80), "white").save(img_path)

    mask = Image.new("L", (120, 80), 0)
    draw = ImageDraw.Draw(mask)
    draw.rectangle([10, 10, 30, 30], fill=255)
    draw.rectangle([70, 40, 90, 60], fill=255)
    mask.save(mask_path)

    ctx = TaskContext(image_path=str(img_path))
    ctx.mask_path = str(mask_path)

    from core.debug_artifacts import DebugArtifactWriter

    writer = DebugArtifactWriter(output_dir=tmp_path, enabled=True)
    out_path = writer.write_mask(ctx)

    assert out_path.exists()
    overlay_path = tmp_path / str(ctx.task_id) / "05_inpaint_mask_cc_overlay.png"
    assert overlay_path.exists()


def test_debug_writer_outputs_grouped_mask_overlay(tmp_path: Path):
    img_path = tmp_path / "blank.png"
    mask_path = tmp_path / "mask.png"
    Image.new("RGB", (120, 80), "white").save(img_path)

    mask = Image.new("L", (120, 80), 0)
    draw = ImageDraw.Draw(mask)
    draw.rectangle([10, 10, 30, 30], fill=255)
    draw.rectangle([70, 40, 90, 60], fill=255)
    mask.save(mask_path)

    ctx = TaskContext(image_path=str(img_path))
    ctx.mask_path = str(mask_path)
    ctx.regions = [
        RegionData(box_2d=Box2D(x1=5, y1=5, x2=40, y2=40)),
        RegionData(box_2d=Box2D(x1=60, y1=35, x2=100, y2=70)),
    ]

    from core.debug_artifacts import DebugArtifactWriter

    writer = DebugArtifactWriter(output_dir=tmp_path, enabled=True)
    writer.write_mask(ctx)

    grouped_path = tmp_path / str(ctx.task_id) / "05_inpaint_mask_cc_grouped_overlay.png"
    assert grouped_path.exists()
