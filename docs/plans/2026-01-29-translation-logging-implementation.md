# Translation Logging Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add structured, per-module logging for translation and AI translation with date-based subdirectories.

**Architecture:** Extend `core/logging_config.setup_module_logger` to create nested log directories (module/date) and reuse file handlers. Add log-level parsing helper, then wire module loggers into `core/modules/translator.py` and `core/ai_translator.py` with concise, safe logging (lengths/snippets only in DEBUG).

**Tech Stack:** Python 3, logging, pytest.

### Task 1: Add date-based subdirectory support to module logger

**Files:**
- Modify: `core/logging_config.py`
- Modify: `tests/test_logging_config.py`

**Step 1: Write the failing test**

```python
import importlib
from datetime import datetime
from pathlib import Path


def test_setup_module_logger_creates_subdir(tmp_path, monkeypatch):
    monkeypatch.setenv("MANHUA_LOG_DIR", str(tmp_path))

    import core.logging_config as logging_config
    importlib.reload(logging_config)

    logging_config.setup_module_logger("test_logger", "translator/translator.log")

    date_str = datetime.now().strftime("%Y%m%d")
    expected = tmp_path / "translator" / date_str / "translator.log"
    assert expected.exists()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_logging_config.py::test_setup_module_logger_creates_subdir -v`
Expected: FAIL (path not created).

**Step 3: Write minimal implementation**

Update `setup_module_logger()` to:
- Accept `log_file` with subdirs
- Create `LOG_DIR / <subdir> / <date>`
- Use `<date>` as directory instead of filename prefix

Example:
```python
    date_str = datetime.now().strftime("%Y%m%d")
    log_path = LOG_DIR / log_file
    if log_path.parent != LOG_DIR:
        log_path = log_path.parent / date_str / log_path.name
    else:
        log_path = LOG_DIR / f"{date_str}_{log_file}"
    log_path.parent.mkdir(parents=True, exist_ok=True)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_logging_config.py::test_setup_module_logger_creates_subdir -v`
Expected: PASS

**Step 5: Commit**

```bash
git add core/logging_config.py tests/test_logging_config.py
git commit -m "feat: add date-based module log directories"
```

### Task 2: Add log level helper for env overrides

**Files:**
- Modify: `core/logging_config.py`
- Modify: `tests/test_logging_config.py`

**Step 1: Write the failing test**

```python
import importlib
import logging


def test_get_log_level_from_env(monkeypatch):
    monkeypatch.setenv("TRANSLATOR_LOG_LEVEL", "DEBUG")

    import core.logging_config as logging_config
    importlib.reload(logging_config)

    assert logging_config.get_log_level("TRANSLATOR_LOG_LEVEL") == logging.DEBUG
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_logging_config.py::test_get_log_level_from_env -v`
Expected: FAIL (function missing).

**Step 3: Write minimal implementation**

Add helper:
```python
def get_log_level(env_var: str, default: int = logging.INFO) -> int:
    value = os.getenv(env_var, "").upper().strip()
    if not value:
        return default
    return getattr(logging, value, default)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_logging_config.py::test_get_log_level_from_env -v`
Expected: PASS

**Step 5: Commit**

```bash
git add core/logging_config.py tests/test_logging_config.py
git commit -m "feat: add env log level helper"
```

### Task 3: Wire module loggers into translator and AI translator

**Files:**
- Modify: `core/modules/translator.py`
- Modify: `core/ai_translator.py`

**Step 1: Write the failing test**

```python
import importlib
from pathlib import Path
from datetime import datetime


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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_logging_config.py::test_translator_module_logger_file -v`
Expected: FAIL (logger not created).

**Step 3: Write minimal implementation**

In `core/modules/translator.py`:
- Replace `logger = logging.getLogger(__name__)` with
  ```python
  from core.logging_config import setup_module_logger, get_log_level
  logger = setup_module_logger(
      __name__,
      "translator/translator.log",
      level=get_log_level("TRANSLATOR_LOG_LEVEL", logging.INFO),
  )
  ```
- Add INFO logs for:
  - total regions, groups
  - total translated count, time
- Add DEBUG logs for:
  - group combined length
  - region snippet + target snippet

In `core/ai_translator.py`:
- Same pattern with `ai/ai_translator.log` and `AI_TRANSLATOR_LOG_LEVEL`
- Log model, request length, duration, and error types (no full content)

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_logging_config.py::test_translator_module_logger_file -v`
Expected: PASS

**Step 5: Commit**

```bash
git add core/modules/translator.py core/ai_translator.py tests/test_logging_config.py
git commit -m "feat: add module logs for translation"
```

### Task 4: Full test run

**Step 1: Run tests**

Run: `pytest -v`
Expected: PASS

**Step 2: Commit (if needed)**

```bash
git status
```
