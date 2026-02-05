import pytest

from core.utils.stderr_suppressor import suppress_native_stderr


def test_suppress_native_stderr_context_manager():
    with suppress_native_stderr():
        assert True


def test_suppress_native_stderr_preserves_inner_exception_when_restore_fails(monkeypatch):
    import core.utils.stderr_suppressor as suppressor_mod

    real_dup2 = suppressor_mod.os.dup2
    calls = {"count": 0, "raised": False}

    def flaky_dup2(src, dst):
        calls["count"] += 1
        # Fail exactly once during restore path, then delegate normally.
        if calls["count"] == 2 and not calls["raised"]:
            calls["raised"] = True
            # Keep fd state valid for pytest capture, then inject failure.
            real_dup2(src, dst)
            raise OSError("restore stderr failed")
        return real_dup2(src, dst)

    monkeypatch.setattr(suppressor_mod.os, "dup2", flaky_dup2)

    with pytest.raises(RuntimeError, match="boom"):
        with suppress_native_stderr():
            raise RuntimeError("boom")
