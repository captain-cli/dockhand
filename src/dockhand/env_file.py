""".env file reading and writing."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional


def parse_env_file(env_file: Optional[str]) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not env_file or not Path(env_file).exists():
        return values

    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def get_env_reserved_port(env_file: Optional[str], env_var_name: str) -> Optional[int]:
    raw = parse_env_file(env_file).get(env_var_name)
    if raw is None:
        raw = os.environ.get(env_var_name)
    if raw is None:
        return None
    try:
        value = int(str(raw))
    except (TypeError, ValueError):
        return None
    return value if 1 <= value <= 65535 else None


def update_env_file(env_file: str, env_var_name: str, port: int) -> None:
    path = Path(env_file)
    path.parent.mkdir(parents=True, exist_ok=True)

    lines: List[str] = []
    found = False
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()

    updated: List[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key, _ = stripped.split("=", 1)
            if key.strip() == env_var_name:
                updated.append(f"{env_var_name}={port}")
                found = True
                continue
        updated.append(line)

    if not found:
        updated.append(f"{env_var_name}={port}")

    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text("\n".join(updated) + "\n", encoding="utf-8")
    os.replace(tmp_path, path)
