"""Naming and identifier helpers."""

from __future__ import annotations

import os
import platform
import re
from pathlib import Path

from .output import fail


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9_.-]+", "-", value)
    value = re.sub(r"-+", "-", value)
    return value.strip("-._")


def env_key(value: str) -> str:
    """Convert arbitrary text to an env-friendly uppercase token."""
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", value.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned.upper()


def default_env_var_name(project_name: str, application_name: str, setting_name: str) -> str:
    parts = [env_key(project_name), env_key(application_name), env_key(setting_name)]
    return "_".join(part for part in parts if part)


def default_config_dir(project_name: str) -> Path:
    """Return a sane per-user config directory for the current OS."""
    safe_project = slugify(project_name) or "dockhand"
    if platform.system() == "Windows":
        root = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(root) / safe_project
    root = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(root) / safe_project


def validate_identifier(value: str, label: str) -> None:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        fail(f"Invalid {label}: {value!r}. Use only letters, numbers, and underscores; do not start with a number.")
