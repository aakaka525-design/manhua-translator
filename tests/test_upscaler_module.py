import asyncio
from pathlib import Path
import subprocess
import pytest

from core.models import TaskContext
from core.modules.upscaler import UpscaleModule


def _make_context(tmp_path: Path) -> TaskContext:
    source = tmp_path / "input.png"
    output = tmp_path / "translated.png"
    source.write_bytes(b"fake")
    output.write_bytes(b"fake")
    return TaskContext(image_path=str(source), output_path=str(output))


def test_upscaler_skips_when_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("UPSCALE_ENABLE", "0")
    ctx = _make_context(tmp_path)
    module = UpscaleModule(binary_path=str(tmp_path / "missing"))

    def _boom(*args, **kwargs):
        raise AssertionError("subprocess should not run")

    monkeypatch.setattr(subprocess, "run", _boom)
    asyncio.run(module.process(ctx))


def test_upscaler_missing_binary_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("UPSCALE_ENABLE", "1")
    ctx = _make_context(tmp_path)
    module = UpscaleModule(binary_path=str(tmp_path / "missing"))

    with pytest.raises(FileNotFoundError):
        asyncio.run(module.process(ctx))


def test_upscaler_replaces_output_with_temp(monkeypatch, tmp_path):
    monkeypatch.setenv("UPSCALE_ENABLE", "1")
    monkeypatch.setenv("UPSCALE_MODEL", "realesrgan-x4plus-anime")
    monkeypatch.setenv("UPSCALE_SCALE", "2")

    binary = tmp_path / "realesrgan-ncnn-vulkan"
    binary.write_text("bin")
    binary.chmod(0o755)

    ctx = _make_context(tmp_path)
    module = UpscaleModule(binary_path=str(binary))
    calls = {}

    def _fake_run(cmd, capture_output, text, check, timeout, cwd=None):
        out_path = Path(cmd[cmd.index("-o") + 1])
        out_path.write_bytes(b"upscaled")
        calls["cmd"] = cmd
        calls["cwd"] = cwd
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="Vulkan")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    asyncio.run(module.process(ctx))
    assert Path(ctx.output_path).read_bytes() == b"upscaled"
    assert "realesrgan-x4plus-anime" in calls["cmd"]
    assert calls["cwd"] == str(binary.parent)
