import importlib
from datetime import datetime
from pathlib import Path


def test_setup_module_logger_respects_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MANHUA_LOG_DIR", str(tmp_path))

    import core.logging_config as logging_config
    importlib.reload(logging_config)

    logging_config.setup_module_logger("test_logger", "test.log")

    date_str = datetime.now().strftime("%Y%m%d")
    expected = tmp_path / f"{date_str}_test.log"
    assert expected.exists()
