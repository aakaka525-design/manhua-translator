"""
Dev wrapper for the main CLI entrypoint.

Use `python main.py ...` for stable CLI behavior.
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    from main import main as app_main

    app_main()


if __name__ == "__main__":
    main()
