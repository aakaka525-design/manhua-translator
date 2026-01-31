from core.pipeline import Pipeline
from core.modules.base import BaseModule
from core.modules.translator import TranslatorModule
from core.crosspage_carryover import CrosspageCarryOverStore


class _NoopModule(BaseModule):
    async def process(self, context):
        return context


def test_pipeline_wires_carryover_store(tmp_path, monkeypatch):
    carry_path = tmp_path / "carryover.jsonl"
    monkeypatch.setenv("CROSSPAGE_CARRYOVER_PATH", str(carry_path))

    pipeline = Pipeline(
        ocr=_NoopModule(),
        translator=TranslatorModule(use_mock=True, use_ai=False),
        inpainter=_NoopModule(),
        renderer=_NoopModule(),
    )

    store = getattr(pipeline.translator, "_carryover_store", None)
    assert isinstance(store, CrosspageCarryOverStore)
    assert store.path == carry_path
