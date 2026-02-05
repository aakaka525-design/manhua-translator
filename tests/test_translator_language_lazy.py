from unittest.mock import patch

import pytest

from core.modules.translator import TranslatorModule
from core.models import RegionData, Box2D
from core.models import TaskContext


def test_translator_uses_current_settings_language():
    region = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
        source_text="hello",
        target_text="",
    )
    translator = TranslatorModule()

    with patch("app.deps.get_settings") as get_settings:
        get_settings.return_value.source_language = "ja"
        get_settings.return_value.target_language = "zh-CN"
        translator._refresh_lang_from_settings()
        assert translator.source_lang == "ja"
        assert translator.target_lang == "zh-CN"


@pytest.mark.asyncio
async def test_translator_refresh_called_on_process():
    translator = TranslatorModule()
    called = {"hit": False}

    def _fake_refresh():
        called["hit"] = True

    translator._refresh_lang_from_settings = _fake_refresh

    ctx = TaskContext(image_path="/tmp/input.png", regions=[])
    await translator.process(ctx)

    assert called["hit"]
