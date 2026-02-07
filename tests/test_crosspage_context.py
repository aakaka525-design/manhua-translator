from core.models import RegionData, Box2D


def test_regiondata_accepts_crosspage_fields():
    region = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
        source_text="hi",
        edge_role="current_bottom",
        edge_box_2d=Box2D(x1=0, y1=-10, x2=10, y2=0),
        skip_translation=True,
        crosspage_texts=["next part"],
    )
    assert region.edge_role == "current_bottom"
    assert region.edge_box_2d.y1 == -10
    assert region.skip_translation is True
    assert region.crosspage_texts == ["next part"]

from core.vision.ocr.postprocessing import build_edge_box, match_crosspage_regions


def test_build_edge_box_bottom_band():
    region = RegionData(box_2d=Box2D(x1=0, y1=90, x2=10, y2=100))
    edge = build_edge_box(region, band_height=20, image_height=100, edge="bottom")
    assert edge.y1 == -10 and edge.y2 == 0


def test_match_crosspage_regions_by_edge_box():
    bottom = RegionData(edge_box_2d=Box2D(x1=0, y1=-8, x2=10, y2=-2))
    top = RegionData(edge_box_2d=Box2D(x1=1, y1=1, x2=9, y2=7))
    assert match_crosspage_regions(bottom, top, x_overlap=0.5, y_gap=5) is True

from core.vision.ocr.paddle_engine import PaddleOCREngine


def test_pair_id_ignores_bottom_variance():
    from core.modules.ocr import OCRModule

    top = RegionData(
        box_2d=Box2D(x1=10, y1=2, x2=20, y2=12),
        source_text="HELLO",
    )
    bottom_a = RegionData(box_2d=Box2D(x1=0, y1=470, x2=50, y2=490))
    bottom_b = RegionData(box_2d=Box2D(x1=200, y1=470, x2=250, y2=490))

    pid_a = OCRModule._pair_id_for_regions(bottom_a, top)
    pid_b = OCRModule._pair_id_for_regions(bottom_b, top)

    assert pid_a == pid_b


def test_pair_id_tolerates_small_top_shift():
    from core.modules.ocr import OCRModule

    bottom = RegionData(box_2d=Box2D(x1=0, y1=470, x2=50, y2=490))
    top_a = RegionData(
        box_2d=Box2D(x1=100, y1=0, x2=150, y2=10),
        source_text="HELLO",
    )
    top_b = RegionData(
        box_2d=Box2D(x1=101, y1=1, x2=151, y2=11),
        source_text="HELLO",
    )

    pid_a = OCRModule._pair_id_for_regions(bottom, top_a)
    pid_b = OCRModule._pair_id_for_regions(bottom, top_b)

    assert pid_a == pid_b


def test_detect_and_recognize_band_accepts_edge(tmp_path):
    engine = PaddleOCREngine(lang="en")
    assert hasattr(engine, "detect_and_recognize_band")


def test_ocr_module_marks_skip_translation_on_top_band(tmp_path):
    import asyncio
    from pathlib import Path
    from PIL import Image

    from core.models import TaskContext
    from core.modules.ocr import OCRModule

    # create simple adjacent pages
    for name in ("1.jpg", "2.jpg", "3.jpg"):
        Image.new("RGB", (100, 1000), (255, 255, 255)).save(tmp_path / name)

    class FakeEngine:
        lang = "en"

        async def detect_and_recognize(self, image_path: str):
            # current page has a top-boundary region
            return [
                RegionData(
                    box_2d=Box2D(x1=0, y1=0, x2=20, y2=10),
                    source_text="A",
                )
            ]

        async def detect_and_recognize_band(self, image_path: str, edge: str, band_height: int):
            if Path(image_path).name == "1.jpg" and edge == "bottom":
                return [
                            RegionData(
                                box_2d=Box2D(x1=0, y1=135, x2=20, y2=150),
                                source_text="가",
                                confidence=0.9,
                            )
                ]
            return []

    module = OCRModule(use_mock=True)
    module.engine = FakeEngine()

    ctx = TaskContext(image_path=str(tmp_path / "2.jpg"), source_language="en")
    result = asyncio.run(module.process(ctx))

    assert result.regions[0].skip_translation is True


def test_crosspage_pair_id_assigned(tmp_path, monkeypatch):
    from PIL import Image
    from core.modules.ocr import OCRModule

    class _FakeEngine:
        lang = "korean"

        async def detect_and_recognize(self, image_path: str):
            from core.models import Box2D, RegionData
            return [
                RegionData(box_2d=Box2D(x1=0, y1=90, x2=50, y2=100), source_text="AAA")
            ]

        async def detect_and_recognize_band(self, image_path: str, edge: str, band_height: int):
            from core.models import Box2D, RegionData
            if edge == "top":
                return [
                    RegionData(
                        box_2d=Box2D(x1=0, y1=0, x2=50, y2=10),
                        source_text="BBB",
                        confidence=0.9,
                    )
                ]
            return []

    module = OCRModule(use_mock=True)
    module.engine = _FakeEngine()

    for name in ("1.jpg", "2.jpg"):
        Image.new("RGB", (100, 100), (255, 255, 255)).save(tmp_path / name)

    from core.models import TaskContext
    ctx = TaskContext(image_path=str(tmp_path / "1.jpg"), source_language="korean")

    result = __import__("asyncio").run(module.process(ctx))
    assert result.regions[0].crosspage_pair_id is not None
    assert result.regions[0].crosspage_role == "current_bottom"


def test_ocr_result_cache_hits_on_second_run(tmp_path, monkeypatch):
    import asyncio
    from PIL import Image

    from core.models import TaskContext
    from core.modules.ocr import OCRModule

    monkeypatch.setenv("OCR_RESULT_CACHE_ENABLE", "1")
    monkeypatch.setenv("OCR_CROSSPAGE_EDGE_ENABLE", "0")
    monkeypatch.setenv("OCR_RESULT_CACHE_DIR", str(tmp_path / "ocr-cache"))

    image_path = tmp_path / "1.jpg"
    Image.new("RGB", (120, 120), (255, 255, 255)).save(image_path)

    calls = {"detect": 0}

    class _FakeEngine:
        lang = "en"
        last_tile_avg_ms = None

        async def detect_and_recognize(self, _image_path: str):
            calls["detect"] += 1
            return [
                RegionData(
                    box_2d=Box2D(x1=10, y1=10, x2=30, y2=30),
                    source_text="HELLO",
                    confidence=0.9,
                )
            ]

    module = OCRModule(use_mock=True)
    module.engine = _FakeEngine()

    ctx1 = TaskContext(image_path=str(image_path), source_language="en")
    ctx2 = TaskContext(image_path=str(image_path), source_language="en")
    asyncio.run(module.process(ctx1))
    asyncio.run(module.process(ctx2))

    assert calls["detect"] == 1
    assert (ctx2.regions[0].source_text or "").strip() == "HELLO"


def test_ocr_crosspage_can_be_disabled(tmp_path, monkeypatch):
    import asyncio
    from PIL import Image

    from core.models import TaskContext
    from core.modules.ocr import OCRModule

    monkeypatch.setenv("OCR_CROSSPAGE_EDGE_ENABLE", "0")
    monkeypatch.setenv("OCR_RESULT_CACHE_ENABLE", "0")

    for name in ("1.jpg", "2.jpg", "3.jpg"):
        Image.new("RGB", (100, 1000), (255, 255, 255)).save(tmp_path / name)

    class _FakeEngine:
        lang = "en"

        async def detect_and_recognize(self, _image_path: str):
            return [
                RegionData(
                    box_2d=Box2D(x1=0, y1=0, x2=20, y2=10),
                    source_text="A",
                    confidence=0.9,
                )
            ]

        async def detect_and_recognize_band(self, _image_path: str, edge: str, band_height: int):
            raise AssertionError(f"crosspage should be disabled, but band OCR called: {edge}/{band_height}")

    module = OCRModule(use_mock=True)
    module.engine = _FakeEngine()

    ctx = TaskContext(image_path=str(tmp_path / "2.jpg"), source_language="en")
    result = asyncio.run(module.process(ctx))
    assert len(result.regions) == 1


def test_translator_appends_crosspage_texts_and_skips():
    import asyncio
    from core.models import TaskContext
    from core.modules.translator import TranslatorModule

    a = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
        source_text="A",
        crosspage_texts=["B"],
    )
    b = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
        source_text="C",
        skip_translation=True,
    )
    ctx = TaskContext(image_path="/tmp/x.png", regions=[a, b])
    module = TranslatorModule(use_mock=True)
    result = asyncio.run(module.process(ctx))

    assert "B" in (result.regions[0].target_text or "")
    assert result.regions[1].target_text == ""


def test_translator_writes_carryover(tmp_path):
    import asyncio
    from core.modules.translator import TranslatorModule
    from core.crosspage_carryover import CrosspageCarryOverStore
    from core.models import TaskContext

    store = CrosspageCarryOverStore(tmp_path / "_carryover.jsonl")

    region = RegionData(
        box_2d=Box2D(x1=0, y1=90, x2=50, y2=100),
        source_text="AAA",
        crosspage_texts=["BBB"],
        crosspage_pair_id="p1",
        crosspage_role="current_bottom",
    )

    module = TranslatorModule(use_ai=False, use_mock=True)
    module._carryover_store = store

    ctx = TaskContext(image_path="/tmp/1.jpg", target_language="zh-CN", regions=[region])
    asyncio.run(module.process(ctx))

    assert store.get("p1") is not None


def test_translator_consumes_carryover(tmp_path):
    import asyncio
    from core.modules.translator import TranslatorModule
    from core.crosspage_carryover import CrosspageCarryOverStore
    from core.models import TaskContext

    store = CrosspageCarryOverStore(tmp_path / "_carryover.jsonl")
    store.put(pair_id="p1", bottom_text="BOTTOM", from_page="1.jpg", to_page="2.jpg")

    region = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=50, y2=10),
        source_text="BBB",
        crosspage_pair_id="p1",
        crosspage_role="next_top",
    )

    module = TranslatorModule(use_ai=False, use_mock=True)
    module._carryover_store = store

    ctx = TaskContext(image_path="/tmp/2.jpg", target_language="zh-CN", regions=[region])
    asyncio.run(module.process(ctx))

    assert region.target_text == "BOTTOM"
    assert store.get("p1") is None


def test_next_top_falls_back_without_carryover():
    import asyncio
    from core.models import TaskContext
    from core.modules.translator import TranslatorModule

    module = TranslatorModule(use_mock=True, use_ai=False)
    region = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
        source_text="당했던",
        crosspage_role="next_top",
        crosspage_pair_id="pair-1",
        skip_translation=True,
    )
    ctx = TaskContext(image_path="/tmp/input.png", target_language="zh-CN", regions=[region])

    result = asyncio.run(module.process(ctx))

    assert result.regions[0].target_text == "[翻译] 당했던"
    assert result.regions[0].skip_translation is False


def test_translator_uses_json_output_for_crosspage(monkeypatch):
    import asyncio
    from core.models import TaskContext
    from core.modules.translator import TranslatorModule

    captured = {}

    class FakeAI:
        model = "fake"

        async def translate_batch(self, texts, output_format="numbered", contexts=None):
            captured["output_format"] = output_format
            return ['{"top":"上","bottom":"下"}']

    module = TranslatorModule(use_mock=False, use_ai=True)
    monkeypatch.setattr(module, "_get_ai_translator", lambda: FakeAI())

    region = RegionData(
        box_2d=Box2D(x1=0, y1=90, x2=50, y2=100),
        source_text="AAA",
        crosspage_texts=["BBB"],
        crosspage_pair_id="p1",
        crosspage_role="current_bottom",
    )

    ctx = TaskContext(image_path="/tmp/x.png", target_language="zh-CN", regions=[region])
    asyncio.run(module.process(ctx))

    assert captured["output_format"] == "json"


def test_translator_records_crosspage_raw_output(monkeypatch):
    import asyncio
    from pathlib import Path
    from core.models import TaskContext
    from core.modules.translator import TranslatorModule
    from core.crosspage_carryover import CrosspageCarryOverStore

    class FakeAI:
        model = "fake"

        async def translate_batch(self, texts, output_format="numbered", contexts=None):
            return ['{"top":"上","bottom":"下"}']

    module = TranslatorModule(use_mock=False, use_ai=True)
    monkeypatch.setattr(module, "_get_ai_translator", lambda: FakeAI())
    module._carryover_store = CrosspageCarryOverStore(Path("/tmp/_carryover.jsonl"))

    region = RegionData(
        box_2d=Box2D(x1=0, y1=90, x2=50, y2=100),
        source_text="AAA",
        crosspage_texts=["BBB"],
        crosspage_pair_id="p1",
        crosspage_role="current_bottom",
    )

    ctx = TaskContext(image_path="/tmp/x.png", target_language="zh-CN", regions=[region])
    ctx.crosspage_debug = {}
    asyncio.run(module.process(ctx))

    assert ctx.crosspage_debug["translations"][0]["raw_output"] == '{"top":"上","bottom":"下"}'


def test_crosspage_bottom_empty_translates_extra(monkeypatch):
    import asyncio
    from pathlib import Path

    from core.crosspage_carryover import CrosspageCarryOverStore
    from core.models import TaskContext
    from core.modules.translator import TranslatorModule

    class FakeAI:
        model = "fake"

        def __init__(self):
            self.calls = []

        async def translate_batch(self, texts, output_format="numbered", contexts=None):
            self.calls.append((list(texts), output_format))
            if output_format == "json":
                return ['{"top":"上","bottom":""}']
            return ["下"]

    fake_ai = FakeAI()
    module = TranslatorModule(use_mock=False, use_ai=True)
    monkeypatch.setattr(module, "_get_ai_translator", lambda: fake_ai)
    module._carryover_store = CrosspageCarryOverStore(Path("/tmp/_carryover.jsonl"))

    region = RegionData(
        box_2d=Box2D(x1=0, y1=90, x2=50, y2=100),
        source_text="AAA",
        crosspage_texts=["BBB"],
        crosspage_pair_id="p1",
        crosspage_role="current_bottom",
    )

    ctx = TaskContext(image_path="/tmp/x.png", target_language="zh-CN", regions=[region])
    asyncio.run(module.process(ctx))

    assert module._carryover_store.get("p1") == "下"
    assert fake_ai.calls[0][1] == "json"


def test_crosspage_bottom_retranslate_same_as_source_not_stored(monkeypatch):
    import asyncio
    from pathlib import Path

    from core.crosspage_carryover import CrosspageCarryOverStore
    from core.models import TaskContext
    from core.modules.translator import TranslatorModule

    class FakeAI:
        model = "fake"

        async def translate_batch(self, texts, output_format="numbered", contexts=None):
            if output_format == "json":
                return ['{"top":"上","bottom":""}']
            return [texts[0]]

    module = TranslatorModule(use_mock=False, use_ai=True)
    monkeypatch.setattr(module, "_get_ai_translator", lambda: FakeAI())
    module._carryover_store = CrosspageCarryOverStore(Path("/tmp/_carryover.jsonl"))

    region = RegionData(
        box_2d=Box2D(x1=0, y1=90, x2=50, y2=100),
        source_text="AAA",
        crosspage_texts=["BBB"],
        crosspage_pair_id="p1",
        crosspage_role="current_bottom",
    )

    ctx = TaskContext(image_path="/tmp/x.png", target_language="zh-CN", regions=[region])
    asyncio.run(module.process(ctx))

    assert module._carryover_store.get("p1") is None


def test_crosspage_bottom_retranslate_hangul_rejected(monkeypatch):
    import asyncio
    from pathlib import Path

    from core.crosspage_carryover import CrosspageCarryOverStore
    from core.models import TaskContext
    from core.modules.translator import TranslatorModule

    class FakeAI:
        model = "fake"

        async def translate_batch(self, texts, output_format="numbered", contexts=None):
            if output_format == "json":
                return ['{"top":"上","bottom":""}']
            return ["당했던 걸"]

    module = TranslatorModule(use_mock=False, use_ai=True)
    monkeypatch.setattr(module, "_get_ai_translator", lambda: FakeAI())
    module._carryover_store = CrosspageCarryOverStore(Path("/tmp/_carryover.jsonl"))

    region = RegionData(
        box_2d=Box2D(x1=0, y1=90, x2=50, y2=100),
        source_text="AAA",
        crosspage_texts=["BBB"],
        crosspage_pair_id="p1",
        crosspage_role="current_bottom",
    )

    ctx = TaskContext(image_path="/tmp/x.png", target_language="zh-CN", regions=[region])
    asyncio.run(module.process(ctx))

    assert module._carryover_store.get("p1") is None


def test_crosspage_bottom_retranslate_jamo_rejected(monkeypatch):
    import asyncio
    from pathlib import Path

    from core.crosspage_carryover import CrosspageCarryOverStore
    from core.models import TaskContext
    from core.modules.translator import TranslatorModule

    class FakeAI:
        model = "fake"

        async def translate_batch(self, texts, output_format="numbered", contexts=None):
            if output_format == "json":
                return ['{"top":"上","bottom":""}']
            return ["当时的 mㄴ"]

    module = TranslatorModule(use_mock=False, use_ai=True)
    monkeypatch.setattr(module, "_get_ai_translator", lambda: FakeAI())
    module._carryover_store = CrosspageCarryOverStore(Path("/tmp/_carryover.jsonl"))

    region = RegionData(
        box_2d=Box2D(x1=0, y1=90, x2=50, y2=100),
        source_text="AAA",
        crosspage_texts=["BBB"],
        crosspage_pair_id="p1",
        crosspage_role="current_bottom",
    )

    ctx = TaskContext(image_path="/tmp/x.png", target_language="zh-CN", regions=[region])
    asyncio.run(module.process(ctx))

    assert module._carryover_store.get("p1") is None


def test_quality_report_includes_crosspage_debug(tmp_path, monkeypatch):
    import json
    from pathlib import Path

    from core.models import TaskContext, PipelineResult
    from core.quality_report import write_quality_report

    monkeypatch.setenv("QUALITY_REPORT_DIR", str(tmp_path))
    ctx = TaskContext(image_path="/tmp/x.png")
    ctx.crosspage_debug = {
        "prev_bottom": [{"source_text": "A", "box_2d": {"x1": 0, "y1": 0, "x2": 10, "y2": 5}}],
        "next_top": [],
    }
    result = PipelineResult(success=True, task=ctx)
    report_path = write_quality_report(result)

    data = json.loads(Path(report_path).read_text())
    assert data["crosspage_debug"]["prev_bottom"][0]["source_text"] == "A"


def test_crosspage_end_to_end_mock_ocr(tmp_path):
    import asyncio
    from pathlib import Path

    from core.models import TaskContext
    from core.pipeline import Pipeline

    (tmp_path / "1.jpg").write_bytes(b"x")
    (tmp_path / "2.jpg").write_bytes(b"x")

    class _MockOCR:
        lang = "en"

        async def detect_and_recognize(self, image_path: str):
            if image_path.endswith("1.jpg"):
                return [RegionData(box_2d=Box2D(x1=0, y1=90, x2=50, y2=100), source_text="He")]
            return [RegionData(box_2d=Box2D(x1=0, y1=0, x2=50, y2=10), source_text="llo")]

        async def detect_and_recognize_band(self, image_path: str, edge: str, band_height: int):
            if image_path.endswith("2.jpg") and edge == "top":
                return [RegionData(box_2d=Box2D(x1=0, y1=0, x2=50, y2=10), source_text="llo")]
            return []

    pipeline = Pipeline()
    pipeline.ocr.engine = _MockOCR()
    pipeline.translator.use_mock = True

    ctx1 = TaskContext(image_path=str(tmp_path / "1.jpg"), source_language="en", target_language="en")
    ctx2 = TaskContext(image_path=str(tmp_path / "2.jpg"), source_language="en", target_language="en")

    asyncio.run(pipeline.process(ctx1))
    asyncio.run(pipeline.process(ctx2))

    assert ctx1.regions[0].target_text
    assert ctx2.regions[0].target_text

def test_calc_band_height_limits():
    from core.modules.ocr import OCRModule

    calc = OCRModule._calc_band_height
    assert calc(100) == 100
    assert calc(600) == 128
    assert calc(2000) == 256


def test_crosspage_band_filters_noise_tokens(tmp_path):
    import asyncio
    from pathlib import Path
    from PIL import Image

    from core.models import TaskContext
    from core.modules.ocr import OCRModule

    for name in ("1.jpg", "2.jpg", "3.jpg"):
        Image.new("RGB", (100, 100), (255, 255, 255)).save(tmp_path / name)

    class FakeEngine:
        lang = "en"

        async def detect_and_recognize(self, image_path: str):
            return [
                RegionData(
                    box_2d=Box2D(x1=0, y1=90, x2=20, y2=100),
                    source_text="아래",
                    confidence=0.9,
                )
            ]

        async def detect_and_recognize_band(self, image_path: str, edge: str, band_height: int):
            if Path(image_path).name == "3.jpg" and edge == "top":
                return [
                    RegionData(
                        box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
                        source_text="O",
                        confidence=0.1,
                    ),
                    RegionData(
                        box_2d=Box2D(x1=0, y1=0, x2=20, y2=10),
                        source_text="당했던",
                        confidence=0.9,
                    ),
                ]
            return []

    module = OCRModule(use_mock=True)
    module.engine = FakeEngine()

    ctx = TaskContext(image_path=str(tmp_path / "2.jpg"), source_language="en")
    result = asyncio.run(module.process(ctx))

    assert result.regions[0].crosspage_texts == ["당했던"]


def test_crosspage_pair_id_uses_first_match(tmp_path):
    import asyncio
    import hashlib
    from pathlib import Path
    from PIL import Image

    from core.models import TaskContext
    from core.modules.ocr import OCRModule

    for name in ("1.jpg", "2.jpg"):
        Image.new("RGB", (400, 500), (255, 255, 255)).save(tmp_path / name)

    class FakeEngine:
        lang = "en"

        async def detect_and_recognize(self, image_path: str):
            return [
                RegionData(
                    box_2d=Box2D(x1=0, y1=470, x2=50, y2=490),
                    source_text="BOTTOM",
                    confidence=0.9,
                )
            ]

        async def detect_and_recognize_band(self, image_path: str, edge: str, band_height: int):
            if Path(image_path).name == "2.jpg" and edge == "top":
                return [
                    RegionData(
                        box_2d=Box2D(x1=0, y1=0, x2=50, y2=10),
                        source_text="ABC",
                        confidence=0.9,
                    ),
                    RegionData(
                        box_2d=Box2D(x1=0, y1=20, x2=50, y2=40),
                        source_text="DEF",
                        confidence=0.9,
                    ),
                ]
            return []

    module = OCRModule(use_mock=True)
    module.engine = FakeEngine()

    ctx = TaskContext(image_path=str(tmp_path / "1.jpg"), source_language="en")
    result = asyncio.run(module.process(ctx))

    expected = hashlib.md5("0|0|abc".encode("utf-8")).hexdigest()[:12]
    assert result.regions[0].crosspage_pair_id == expected


def test_skip_translation_regions_are_inpainted():
    from core.modules.inpainter import InpainterModule
    from core.models import TaskContext

    called = {"regions": None}

    class FakeInpainter:
        async def inpaint_regions(self, image_path, regions, output_path, temp_dir, dilation=0):
            called["regions"] = regions
            return output_path

    ctx = TaskContext(
        image_path="/tmp/x.png",
        regions=[
            RegionData(
                box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
                source_text="A",
                skip_translation=True,
                inpaint_mode="erase",
            )
        ],
    )
    module = InpainterModule(inpainter=FakeInpainter(), output_dir="/tmp", use_time_subdir=False)

    __import__("asyncio").run(module.process(ctx))
    assert called["regions"] is not None
    assert called["regions"][0].skip_translation is True
