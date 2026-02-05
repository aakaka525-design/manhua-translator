from __future__ import annotations

import os
from pathlib import Path


def update_env_file(key: str, value: str, env_path: str | None = None) -> None:
    path = Path(env_path or os.getenv("ENV_FILE", ".env"))
    path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()

    found = False
    new_lines: list[str] = []
    for line in lines:
        if not line or line.startswith("#"):
            new_lines.append(line)
            continue
        current_key = line.split("=", 1)[0]
        if current_key == key:
            new_lines.append(f"{key}={value}")
            found = True
        else:
            new_lines.append(line)

    if not found:
        new_lines.append(f"{key}={value}")

    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
