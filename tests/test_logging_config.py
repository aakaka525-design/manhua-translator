import importlib
import logging
import sys
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


def test_setup_module_logger_creates_subdir(tmp_path, monkeypatch):
    monkeypatch.setenv("MANHUA_LOG_DIR", str(tmp_path))

    import core.logging_config as logging_config
    importlib.reload(logging_config)

    logging_config.setup_module_logger("test_logger", "translator/translator.log")

    date_str = datetime.now().strftime("%Y%m%d")
    expected = tmp_path / "translator" / date_str / "translator.log"
    assert expected.exists()


def test_get_log_level_from_env(monkeypatch):
    monkeypatch.setenv("TRANSLATOR_LOG_LEVEL", "DEBUG")

    import core.logging_config as logging_config
    importlib.reload(logging_config)

    assert logging_config.get_log_level("TRANSLATOR_LOG_LEVEL") == 10


def test_translator_module_logger_file(tmp_path, monkeypatch):
    monkeypatch.setenv("MANHUA_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("TRANSLATOR_LOG_LEVEL", "INFO")

    import core.logging_config as logging_config
    importlib.reload(logging_config)

    import core.modules.translator as translator
    importlib.reload(translator)

    date_str = datetime.now().strftime("%Y%m%d")
    expected = tmp_path / "translator" / date_str / "translator.log"
    assert expected.exists()


def test_setup_module_logger_can_mirror_to_stdout(tmp_path, monkeypatch):
    monkeypatch.setenv("MANHUA_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("AI_TRANSLATOR_LOG_TO_STDOUT", "1")

    import core.logging_config as logging_config
    importlib.reload(logging_config)

    logger = logging_config.setup_module_logger(
        "core.ai_translator",
        "ai/ai_translator.log",
        console_env="AI_TRANSLATOR_LOG_TO_STDOUT",
    )

    has_stdout_handler = any(
        isinstance(handler, logging.StreamHandler)
        and not isinstance(handler, logging.FileHandler)
        and getattr(handler, "stream", None) is sys.stdout
        for handler in logger.handlers
    )
    assert has_stdout_handler is True
