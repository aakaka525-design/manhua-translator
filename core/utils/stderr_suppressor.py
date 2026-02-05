"""Native stderr suppression helpers."""

from __future__ import annotations

import contextlib
import os
import sys


@contextlib.contextmanager
def suppress_native_stderr():
    """Suppress native stderr (C/ObjC NSLog)."""
    if os.getenv("SUPPRESS_NATIVE_STDERR", "1") == "0":
        yield
        return
    if os.getenv("OCR_SUPPRESS_NSLOG") == "0":
        # Backward compatibility for legacy env name
        yield
        return
    try:
        stderr_fd = sys.stderr.fileno()
    except Exception:
        yield
        return
    try:
        saved_stderr = os.dup(stderr_fd)
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, stderr_fd)
        os.close(devnull)
        try:
            yield
        finally:
            os.dup2(saved_stderr, stderr_fd)
            os.close(saved_stderr)
    except (ValueError, OSError):
        yield
