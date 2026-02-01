import asyncio

from core.modules.translator import TranslatorModule
from core.models import Box2D, RegionData, TaskContext


class _FakeAITranslator:
    def __init__(self):
        self.calls = []
        self.model = "fake"

    async def translate_batch(self, texts, output_format="numbered", contexts=None):
        self.calls.append({
            "texts": texts,
            "contexts": contexts,
            "output_format": output_format,
        })
        return [f"译:{t}" for t in texts]


def test_translator_passes_adjacent_contexts(monkeypatch):
    module = TranslatorModule(source_lang="en", target_lang="zh", use_ai=True)
    fake = _FakeAITranslator()
    monkeypatch.setattr(module, "_get_ai_translator", lambda: fake)

    regions = [
        RegionData(
            box_2d=Box2D(x1=0, y1=0, x2=100, y2=40),
            source_text="HELLO",
            confidence=0.9,
        ),
        RegionData(
            box_2d=Box2D(x1=0, y1=200, x2=100, y2=240),
            source_text="MIDDLE",
            confidence=0.9,
        ),
        RegionData(
            box_2d=Box2D(x1=0, y1=400, x2=100, y2=440),
            source_text="BOTTOM",
            confidence=0.9,
        ),
    ]
    ctx = TaskContext(image_path="/tmp/input.png", regions=regions)

    asyncio.run(module.process(ctx))

    assert fake.calls, "expected translate_batch to be called"
    contexts = fake.calls[0]["contexts"]
    assert contexts == ["MIDDLE", "HELLO | BOTTOM", "MIDDLE"]
