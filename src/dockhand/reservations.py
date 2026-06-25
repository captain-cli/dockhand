"""JSON reservation file support."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional


def load_reserved_ports(path: str) -> Dict[str, Dict[str, object]]:
    if not Path(path).exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_reserved_ports(path: str, data: Dict[str, Dict[str, object]]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    os.replace(tmp_path, path)


def reservation_key(project_name: str, application_name: str, setting_name: str) -> str:
    return f"{project_name}:{application_name}:{setting_name}"


def get_reserved_port(reserved_ports: Dict[str, Dict[str, object]], key: str, protocol: str) -> Optional[int]:
    entry = reserved_ports.get(key)
    if not isinstance(entry, dict) or entry.get("protocol") != protocol:
        return None
    port = entry.get("port")
    return port if isinstance(port, int) else None


def reserve_port(
    reserved_ports: Dict[str, Dict[str, object]],
    key: str,
    project_name: str,
    application_name: str,
    setting_name: str,
    port: int,
    protocol: str,
    description: str,
    env_var_name: str,
) -> None:
    reserved_ports[key] = {
        "project_name": project_name,
        "application_name": application_name,
        "setting_name": setting_name,
        "description": description,
        "port": port,
        "protocol": protocol,
        "env_var": env_var_name,
    }


def list_reserved_port_values(reserved_ports: Dict[str, Dict[str, object]], protocol: str, exclude_key: Optional[str] = None) -> List[int]:
    ports: List[int] = []
    for key, entry in reserved_ports.items():
        if exclude_key and key == exclude_key:
            continue
        if not isinstance(entry, dict) or entry.get("protocol") != protocol:
            continue
        port = entry.get("port")
        if isinstance(port, int):
            ports.append(port)
    return ports
