from core.modules.base import BaseModule
from core.models import TaskContext
from core.pipeline import Pipeline


class DummyModule(BaseModule):
    async def process(self, context: TaskContext) -> TaskContext:
        return context


def test_pipeline_stage_order_includes_upscaler():
    pipeline = Pipeline(
        ocr=DummyModule("ocr"),
        translator=DummyModule("translator"),
        inpainter=DummyModule("inpainter"),
        renderer=DummyModule("renderer"),
        upscaler=DummyModule("upscaler"),
    )
    stage_names = [name for name, _ in pipeline.stages]
    assert stage_names == ["ocr", "translator", "inpainter", "renderer", "upscaler"]
