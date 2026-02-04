from pathlib import Path


def test_setup_local_script_exists():
    script = Path("scripts/setup_local.sh")
    assert script.exists()


def test_gitignore_includes_tools_bin():
    content = Path(".gitignore").read_text(encoding="utf-8")
    assert "/tools/bin/" in content
