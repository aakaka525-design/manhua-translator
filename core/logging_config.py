"""
日志配置模块 - 统一管理项目日志输出。

日志文件存储在 logs/ 目录下，按日期和模块分类。
"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# 日志目录（可通过环境变量覆盖）
_env_log_dir = os.getenv("MANHUA_LOG_DIR")
LOG_DIR = (
    Path(_env_log_dir).expanduser()
    if _env_log_dir
    else Path(__file__).parent.parent / "logs"
)


def _ensure_log_dir() -> None:
    global LOG_DIR
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        return
    except OSError:
        # Fallback to a writable temp dir if repo logs are not writable
        fallback = Path(os.getenv("MANHUA_LOG_DIR_FALLBACK", "/tmp/manhua-logs"))
        if fallback != LOG_DIR:
            LOG_DIR = fallback
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            return
        raise


def setup_logging(
    level: int = logging.INFO,
    log_file: Optional[str] = None,
    console: bool = True,
):
    """
    配置全局日志系统。

    Args:
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR)
        log_file: 日志文件名（自动添加日期前缀）
        console: 是否输出到控制台
    """
    # 日志格式
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    _ensure_log_dir()

    # 根 logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # 清除已有 handlers
    root_logger.handlers.clear()

    # 控制台输出
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    # 文件输出
    if log_file:
        try:
            date_str = datetime.now().strftime("%Y%m%d")
            log_path = LOG_DIR / f"{date_str}_{log_file}"
            file_handler = logging.FileHandler(log_path, encoding="utf-8")
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        except OSError:
            # Ignore file handler if we cannot write logs
            pass

    # 抑制第三方库的冗余日志
    logging.getLogger("ppocr").setLevel(logging.WARNING)
    logging.getLogger("paddlex").setLevel(logging.WARNING)
    logging.getLogger("paddle").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    return root_logger


def setup_module_logger(
    name: str,
    log_file: str,
    level: int = logging.INFO,
    console_env: Optional[str] = None,
) -> logging.Logger:
    """
    为指定模块创建独立日志文件（不影响全局 handler）。

    Args:
        name: logger 名称
        log_file: 日志文件名（自动添加日期前缀）
        level: 日志级别
    """
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    _ensure_log_dir()

    date_str = datetime.now().strftime("%Y%m%d")
    log_path = LOG_DIR / log_file
    if log_path.parent != LOG_DIR:
        log_path = log_path.parent / date_str / log_path.name
    else:
        log_path = LOG_DIR / f"{date_str}_{log_file}"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Fallback to temp dir if cannot create module log dir
        fallback = Path(os.getenv("MANHUA_LOG_DIR_FALLBACK", "/tmp/manhua-logs"))
        fallback.mkdir(parents=True, exist_ok=True)
        log_path = fallback / log_path.name
    for handler in logger.handlers:
        if (
            isinstance(handler, logging.FileHandler)
            and Path(handler.baseFilename) == log_path
        ):
            return logger

    try:
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        # If we still cannot write, keep logger without file handler
        pass

    # Optional: mirror module logs to container stdout for easier docker logs debugging.
    def _is_truthy(value: str) -> bool:
        return value.strip().lower() not in {"", "0", "false", "off", "no"}

    enable_console = _is_truthy(os.getenv("MODULE_LOG_TO_STDOUT", "0"))
    if console_env:
        enable_console = enable_console or _is_truthy(os.getenv(console_env, "0"))

    if enable_console:
        has_stdout_handler = any(
            isinstance(handler, logging.StreamHandler)
            and not isinstance(handler, logging.FileHandler)
            and getattr(handler, "stream", None) is sys.stdout
            for handler in logger.handlers
        )
        if not has_stdout_handler:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(level)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    获取指定名称的 logger。

    Args:
        name: logger 名称（通常使用 __name__）

    Returns:
        配置好的 Logger 实例
    """
    return logging.getLogger(name)


def get_log_level(env_var: str, default: int = logging.INFO) -> int:
    """
    从环境变量读取日志级别，默认 INFO。

    Args:
        env_var: 环境变量名
        default: 默认日志级别

    Returns:
        日志级别（logging.INFO 等）
    """
    value = os.getenv(env_var, "").upper().strip()
    if not value:
        return default
    return getattr(logging, value, default)


# 默认初始化
_initialized = False


def init_default_logging():
    """初始化默认日志配置。"""
    global _initialized
    if not _initialized:
        setup_logging(
            level=logging.INFO,
            log_file="app.log",
            console=True,
        )
        setup_module_logger("parser", "parser.log")
        _initialized = True


# 导出
__all__ = [
    "setup_logging",
    "setup_module_logger",
    "get_logger",
    "get_log_level",
    "LOG_DIR",
    "init_default_logging",
]
