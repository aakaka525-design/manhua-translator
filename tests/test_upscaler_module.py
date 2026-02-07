import asyncio
from pathlib import Path
import subprocess
import pytest
import numpy as np
import cv2

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
    monkeypatch.setenv("UPSCALE_BACKEND", "ncnn")
    ctx = _make_context(tmp_path)
    module = UpscaleModule(binary_path=str(tmp_path / "missing"))

    def _boom(*args, **kwargs):
        raise AssertionError("subprocess should not run")

    monkeypatch.setattr(subprocess, "run", _boom)
    asyncio.run(module.process(ctx))


def test_upscaler_respects_runtime_enable_override(monkeypatch, tmp_path):
    from app.routes import settings as settings_route

    monkeypatch.setenv("UPSCALE_ENABLE", "1")
    monkeypatch.setenv("UPSCALE_BACKEND", "ncnn")
    settings_route._upscale_enable_override = False

    ctx = _make_context(tmp_path)
    module = UpscaleModule(binary_path=str(tmp_path / "missing"))

    def _boom(*args, **kwargs):
        raise AssertionError("ncnn pipeline should not run when override disables upscale")

    monkeypatch.setattr(module, "_run_ncnn", _boom)
    asyncio.run(module.process(ctx))


def test_upscaler_missing_binary_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("UPSCALE_ENABLE", "1")
    monkeypatch.setenv("UPSCALE_BACKEND", "ncnn")
    ctx = _make_context(tmp_path)
    module = UpscaleModule(binary_path=str(tmp_path / "missing"))

    with pytest.raises(FileNotFoundError):
        asyncio.run(module.process(ctx))


def test_upscaler_replaces_output_with_temp(monkeypatch, tmp_path):
    monkeypatch.setenv("UPSCALE_ENABLE", "1")
    monkeypatch.setenv("UPSCALE_BACKEND", "ncnn")
    monkeypatch.setenv("UPSCALE_MODEL", "realesrgan-x4plus-anime")
    monkeypatch.setenv("UPSCALE_SCALE", "2")

    binary = tmp_path / "realesrgan-ncnn-vulkan"
    binary.write_text("bin")
    binary.chmod(0o755)

    model_dir = tmp_path / "models"
    model_dir.mkdir()
    monkeypatch.setenv("UPSCALE_NCNN_MODEL_DIR", str(model_dir))

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


def test_upscaler_ncnn_uses_absolute_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("UPSCALE_ENABLE", "1")
    monkeypatch.setenv("UPSCALE_BACKEND", "ncnn")
    monkeypatch.setenv("UPSCALE_MODEL", "realesrgan-x4plus-anime")
    monkeypatch.setenv("UPSCALE_SCALE", "2")

    binary = tmp_path / "realesrgan-ncnn-vulkan"
    binary.write_text("bin")
    binary.chmod(0o755)

    model_dir = tmp_path / "models"
    model_dir.mkdir()
    monkeypatch.setenv("UPSCALE_NCNN_MODEL_DIR", str(model_dir))

    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "translated.png"
    out_path.write_bytes(b"fake")

    ctx = TaskContext(image_path=str(out_path), output_path="out/translated.png")
    module = UpscaleModule(binary_path=str(binary))
    calls = {}

    def _fake_run(cmd, capture_output, text, check, timeout, cwd=None):
        calls["cmd"] = cmd
        out_path = Path(cmd[cmd.index("-o") + 1])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"upscaled")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    monkeypatch.chdir(tmp_path)

    asyncio.run(module.process(ctx))

    input_path = Path(calls["cmd"][calls["cmd"].index("-i") + 1])
    output_path = Path(calls["cmd"][calls["cmd"].index("-o") + 1])
    assert input_path.is_absolute()
    assert output_path.is_absolute()


def test_upscaler_ncnn_passes_model_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("UPSCALE_ENABLE", "1")
    monkeypatch.setenv("UPSCALE_BACKEND", "ncnn")
    monkeypatch.setenv("UPSCALE_MODEL", "realesrgan-x4plus-anime")
    monkeypatch.setenv("UPSCALE_SCALE", "2")

    binary = tmp_path / "realesrgan-ncnn-vulkan"
    binary.write_text("bin")
    binary.chmod(0o755)

    model_dir = tmp_path / "models"
    model_dir.mkdir()
    monkeypatch.setenv("UPSCALE_NCNN_MODEL_DIR", str(model_dir))

    out_path = tmp_path / "translated.png"
    out_path.write_bytes(b"fake")

    ctx = TaskContext(image_path=str(out_path), output_path=str(out_path))
    module = UpscaleModule(binary_path=str(binary))
    calls = {}

    def _fake_run(cmd, capture_output, text, check, timeout, cwd=None):
        calls["cmd"] = cmd
        out_path = Path(cmd[cmd.index("-o") + 1])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"upscaled")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    asyncio.run(module.process(ctx))

    assert "-m" in calls["cmd"]
    model_arg = Path(calls["cmd"][calls["cmd"].index("-m") + 1])
    assert model_arg.is_absolute()
    assert model_arg == model_dir


def test_upscaler_ncnn_uses_tile_flag(monkeypatch, tmp_path):
    monkeypatch.setenv("UPSCALE_ENABLE", "1")
    monkeypatch.setenv("UPSCALE_BACKEND", "ncnn")
    monkeypatch.setenv("UPSCALE_MODEL", "realesr-animevideov3-x4")
    monkeypatch.setenv("UPSCALE_SCALE", "4")
    monkeypatch.setenv("UPSCALE_TILE", "256")

    binary = tmp_path / "realesrgan-ncnn-vulkan"
    binary.write_text("bin")
    binary.chmod(0o755)

    model_dir = tmp_path / "models"
    model_dir.mkdir()
    monkeypatch.setenv("UPSCALE_NCNN_MODEL_DIR", str(model_dir))

    out_path = tmp_path / "translated.png"
    out_path.write_bytes(b"fake")

    ctx = TaskContext(image_path=str(out_path), output_path=str(out_path))
    module = UpscaleModule(binary_path=str(binary))
    calls = {}

    def _fake_run(cmd, capture_output, text, check, timeout, cwd=None):
        calls["cmd"] = cmd
        out_path = Path(cmd[cmd.index("-o") + 1])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"upscaled")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    asyncio.run(module.process(ctx))

    assert "-t" in calls["cmd"]
    idx = calls["cmd"].index("-t")
    assert calls["cmd"][idx + 1] == "256"


def test_upscaler_pytorch_missing_model_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("UPSCALE_ENABLE", "1")
    monkeypatch.setenv("UPSCALE_BACKEND", "pytorch")
    monkeypatch.setenv("UPSCALE_MODEL_PATH", str(tmp_path / "missing.pth"))

    ctx = _make_context(tmp_path)
    module = UpscaleModule()

    with pytest.raises(FileNotFoundError):
        asyncio.run(module.process(ctx))


def test_upscaler_pytorch_calls_runner(monkeypatch, tmp_path):
    monkeypatch.setenv("UPSCALE_ENABLE", "1")
    monkeypatch.setenv("UPSCALE_BACKEND", "pytorch")
    model_path = tmp_path / "RealESRGAN_x4plus.pth"
    model_path.write_text("pth")
    monkeypatch.setenv("UPSCALE_MODEL_PATH", str(model_path))

    ctx = _make_context(tmp_path)
    module = UpscaleModule()
    called = {}

    def _fake_run(*args, **kwargs):
        called["ok"] = True
        return None

    monkeypatch.setattr(module, "_run_pytorch", _fake_run)
    asyncio.run(module.process(ctx))
    assert called.get("ok") is True


def test_upscaler_pytorch_registers_torchvision_shim():
    import importlib
    import sys
    pytest.importorskip("torchvision.transforms.functional")

    sys.modules.pop("torchvision.transforms.functional_tensor", None)
    from core.modules import upscaler

    upscaler._ensure_torchvision_functional_tensor()
    ft = importlib.import_module("torchvision.transforms.functional_tensor")
    assert hasattr(ft, "rgb_to_grayscale")


def test_upscaler_torchvision_shim_missing_torchvision_does_not_raise(monkeypatch):
    from core.modules import upscaler

    original_find_spec = upscaler.importlib.util.find_spec

    def _fake_find_spec(name, package=None):
        if name == "torchvision.transforms.functional_tensor":
            raise ModuleNotFoundError("No module named 'torchvision'")
        return original_find_spec(name, package)

    monkeypatch.setattr(upscaler.importlib.util, "find_spec", _fake_find_spec)
    upscaler._ensure_torchvision_functional_tensor()


def test_upscaler_pytorch_device_auto_prefers_mps(monkeypatch):
    import torch
    from core.modules import upscaler

    monkeypatch.setenv("UPSCALE_DEVICE", "auto")
    monkeypatch.setattr(torch.backends.mps, "is_available", lambda: True)

    assert upscaler._resolve_torch_device_name() == "mps"


def test_upscaler_pytorch_device_auto_falls_back_to_cpu(monkeypatch):
    import torch
    from core.modules import upscaler

    monkeypatch.setenv("UPSCALE_DEVICE", "auto")
    monkeypatch.setattr(torch.backends.mps, "is_available", lambda: False)

    assert upscaler._resolve_torch_device_name() == "cpu"


def test_upscaler_pytorch_device_mps_requires_available(monkeypatch):
    import torch
    from core.modules import upscaler

    monkeypatch.setenv("UPSCALE_DEVICE", "mps")
    monkeypatch.setattr(torch.backends.mps, "is_available", lambda: False)

    with pytest.raises(RuntimeError):
        upscaler._resolve_torch_device_name()


def test_upscaler_stripe_timeout_uses_perf_start(monkeypatch, tmp_path):
    import asyncio
    import sys
    import types
    import numpy as np
    import cv2
    import shutil
    from core.modules import upscaler

    monkeypatch.setenv("UPSCALE_ENABLE", "1")
    monkeypatch.setenv("UPSCALE_BACKEND", "pytorch")
    monkeypatch.setenv("UPSCALE_DEVICE", "cpu")
    monkeypatch.setenv("UPSCALE_SCALE", "2")
    monkeypatch.setenv("UPSCALE_TIMEOUT", "1")
    monkeypatch.setenv("UPSCALE_STRIPE_ENABLE", "1")
    monkeypatch.setenv("UPSCALE_STRIPE_THRESHOLD", "4000")
    monkeypatch.setenv("UPSCALE_STRIPE_HEIGHT", "2000")
    monkeypatch.setenv("UPSCALE_STRIPE_OVERLAP", "64")

    model_path = tmp_path / "RealESRGAN_x4plus.pth"
    model_path.write_text("pth")
    monkeypatch.setenv("UPSCALE_MODEL_PATH", str(model_path))

    fake_image = np.zeros((5000, 10, 3), dtype=np.uint8)
    monkeypatch.setattr(cv2, "imread", lambda *args, **kwargs: fake_image)
    monkeypatch.setattr(cv2, "imwrite", lambda *args, **kwargs: True)
    monkeypatch.setattr(shutil, "move", lambda *args, **kwargs: None)

    class _DummyRRDBNet:
        def __init__(self, *args, **kwargs):
            pass

    class _DummyESRGANer:
        def __init__(self, *args, **kwargs):
            pass

        def enhance(self, image, outscale=2):
            h, w = image.shape[:2]
            return np.zeros((h * outscale, w * outscale, 3), dtype=np.uint8), None

    basicsr = types.ModuleType("basicsr")
    basicsr_archs = types.ModuleType("basicsr.archs")
    basicsr_archs_rrdb = types.ModuleType("basicsr.archs.rrdbnet_arch")
    basicsr_archs_rrdb.RRDBNet = _DummyRRDBNet
    sys.modules["basicsr"] = basicsr
    sys.modules["basicsr.archs"] = basicsr_archs
    sys.modules["basicsr.archs.rrdbnet_arch"] = basicsr_archs_rrdb

    realesrgan = types.ModuleType("realesrgan")
    realesrgan.RealESRGANer = _DummyESRGANer
    sys.modules["realesrgan"] = realesrgan

    values = iter([20000.0, 20000.1, 20000.2, 20000.3, 20000.4, 20000.45, 20000.48, 20000.5])
    monkeypatch.setattr(upscaler.time, "perf_counter", lambda: next(values))

    ctx = _make_context(tmp_path)
    module = UpscaleModule()

    asyncio.run(module.process(ctx))


def test_upscaler_cloudrun_backend_is_unsupported(monkeypatch, tmp_path):
    monkeypatch.setenv("UPSCALE_ENABLE", "1")
    monkeypatch.setenv("UPSCALE_BACKEND", "cloudrun")

    ctx = _make_context(tmp_path)
    module = UpscaleModule()

    with pytest.raises(ValueError, match="Unsupported UPSCALE_BACKEND"):
        asyncio.run(module.process(ctx))
