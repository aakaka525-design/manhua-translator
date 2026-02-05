import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
    )


def test_scripts_cli_delegates_to_main():
    result = _run("scripts/cli.py", "--help")
    output = (result.stdout or "") + (result.stderr or "")
    assert result.returncode == 0
    assert "chapter" in output
    assert "translate" not in output


def test_batch_translate_has_no_cli_entrypoint():
    result = _run("batch_translate.py")
    output = (result.stdout or "") + (result.stderr or "")
    assert result.returncode == 0
    assert "用法" not in output
