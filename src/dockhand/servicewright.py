"""Servicewright integration helpers.

Dockhand owns runtime port reconciliation. Servicewright owns systemd rendering.
This module reads a Servicewright config, preserves safe requested ports, assigns
new ports for conflicts/missing values, and writes a resolved config plus env
files for Servicewright to consume.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .errors import PortAllocationError
from .ports import first_available_port, port_is_available
from .reservations import load_reserved_ports, reserve_port, reservation_key, save_reserved_ports

DEFAULT_START_PORT = 41000
DEFAULT_END_PORT = 41999
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PROTOCOL = "tcp"


def _load_json(path: str | Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise PortAllocationError("Servicewright config must be a JSON object")
    return data


def _write_json(path: str | Path, data: Dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def _as_services(config: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], bool]:
    if "services" in config:
        services = config.get("services")
        if not isinstance(services, list) or not services:
            raise PortAllocationError("Servicewright config services must be a non-empty array")
        for service in services:
            if not isinstance(service, dict):
                raise PortAllocationError("Each Servicewright service entry must be an object")
        return services, True
    return [config], False


def _service_name(service: Dict[str, Any]) -> str:
    name = service.get("name")
    if not isinstance(name, str) or not name.strip():
        raise PortAllocationError("Each Servicewright service must define a non-empty name")
    return name.strip()


def _runtime(service: Dict[str, Any]) -> Dict[str, Any]:
    runtime = service.get("runtime")
    if runtime is None:
        runtime = {}
        service["runtime"] = runtime
    if not isinstance(runtime, dict):
        raise PortAllocationError(f"Service {_service_name(service)} runtime must be an object")
    return runtime


def _port_range(runtime: Dict[str, Any], default_start: int, default_end: int) -> Tuple[int, int]:
    raw_range = runtime.get("portRange")
    if isinstance(raw_range, list) and len(raw_range) == 2:
        start, end = int(raw_range[0]), int(raw_range[1])
    else:
        start = int(runtime.get("startPort", default_start))
        end = int(runtime.get("endPort", default_end))
        runtime.setdefault("portRange", [start, end])
    if start < 1 or end > 65535 or start > end:
        raise PortAllocationError(f"Invalid port range {start}-{end}")
    return start, end


def _requested_port(runtime: Dict[str, Any]) -> Optional[int]:
    raw = runtime.get("port")
    if raw is None:
        raw = runtime.get("requestedPort")
    if raw in (None, ""):
        return None
    try:
        port = int(raw)
    except (TypeError, ValueError):
        raise PortAllocationError(f"Invalid requested port: {raw}")
    if not 1 <= port <= 65535:
        raise PortAllocationError(f"Invalid requested port: {port}")
    return port


def _matching_reservation(reserved_ports: Dict[str, Dict[str, Any]], key: str, port: int, protocol: str) -> bool:
    entry = reserved_ports.get(key)
    if not isinstance(entry, dict):
        return False
    return int(entry.get("port", -1)) == int(port) and str(entry.get("protocol", protocol)).lower() == protocol.lower()


def _resolve_env_file_path(service: Dict[str, Any], root: Path, env_dir: Optional[str]) -> Optional[Path]:
    name = _service_name(service)
    if env_dir:
        return (root / env_dir / f"{name}.env").resolve() if not Path(env_dir).is_absolute() else (Path(env_dir) / f"{name}.env")
    raw = service.get("environmentFile") or service.get("environment_file")
    if not raw:
        return None
    path = Path(str(raw))
    return path if path.is_absolute() else (root / path).resolve()


def _write_service_env(path: Path, service_name: str, host: str, port: int, extra: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    values: Dict[str, str] = {
        "SERVICE_NAME": service_name,
        "HOST": host,
        "PORT": str(port),
    }
    for key, value in extra.items():
        if value is None:
            continue
        values[str(key)] = str(value)
    path.write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")


def _env_extra(runtime: Dict[str, Any]) -> Dict[str, Any]:
    extra = runtime.get("env") or runtime.get("environment") or {}
    return extra if isinstance(extra, dict) else {}


def reconcile_servicewright_config(
    *,
    config_path: str,
    write_config: str,
    write_env: Optional[str] = None,
    root: Optional[str] = None,
    reserved_ports_file: Optional[str] = None,
    project_name: Optional[str] = None,
    default_start_port: int = DEFAULT_START_PORT,
    default_end_port: int = DEFAULT_END_PORT,
    protocol: str = DEFAULT_PROTOCOL,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Reconcile a Servicewright config and return a structured summary."""

    source = Path(config_path).resolve()
    project_root = Path(root).resolve() if root else source.parent
    config = _load_json(source)
    resolved = deepcopy(config)
    services, is_collection = _as_services(resolved)
    project = project_name or str(resolved.get("projectName") or resolved.get("project") or project_root.name)

    reservation_file = Path(reserved_ports_file) if reserved_ports_file else project_root / ".captain" / "runtime" / "dockhand-reserved-ports.json"
    reserved_ports = load_reserved_ports(str(reservation_file))
    blocked_ports: set[int] = set()
    results: List[Dict[str, Any]] = []

    for service in services:
        name = _service_name(service)
        runtime = _runtime(service)
        start, end = _port_range(runtime, default_start_port, default_end_port)
        host = str(runtime.get("host", DEFAULT_HOST))
        requested = _requested_port(runtime)
        key = reservation_key(project, name, "port")
        assignment_reason = ""
        assigned: int

        if requested is not None and requested in blocked_ports:
            assigned = first_available_port(start, end, host, protocol, blocked_ports)
            assignment_reason = f"requested port {requested} was already assigned to another service in this run"
        elif requested is not None and _matching_reservation(reserved_ports, key, requested, protocol):
            assigned = requested
            assignment_reason = "requested port already reserved for this service"
        elif requested is not None and port_is_available(host, requested, protocol):
            assigned = requested
            assignment_reason = "requested port available"
        else:
            blocked = set(blocked_ports)
            # Block ports reserved by other services to avoid stealing known assignments.
            for reserved_key, entry in reserved_ports.items():
                if reserved_key == key or not isinstance(entry, dict):
                    continue
                if str(entry.get("protocol", protocol)).lower() != protocol.lower():
                    continue
                try:
                    blocked.add(int(entry.get("port")))
                except (TypeError, ValueError):
                    continue
            assigned = first_available_port(start, end, host, protocol, blocked)
            if requested is None:
                assignment_reason = "no requested port; assigned first available port"
            else:
                assignment_reason = f"requested port {requested} was unavailable or owned by another service"

        blocked_ports.add(assigned)
        runtime["host"] = host
        runtime["port"] = assigned
        runtime["protocol"] = protocol
        runtime["assignedBy"] = "dockhand"
        runtime["assignmentReason"] = assignment_reason
        if requested is not None and requested != assigned:
            runtime["requestedPort"] = requested
        elif requested is None:
            runtime.pop("requestedPort", None)

        env_path = _resolve_env_file_path(service, project_root, write_env)
        if env_path is not None:
            service["environmentFile"] = str(env_path)
            if not dry_run:
                _write_service_env(env_path, name, host, assigned, _env_extra(runtime))

        reserve_port(
            reserved_ports=reserved_ports,
            key=key,
            project_name=project,
            application_name=name,
            setting_name="port",
            port=assigned,
            protocol=protocol,
            description=f"Servicewright runtime port for {name}",
            env_var_name="PORT",
        )

        results.append(
            {
                "serviceName": name,
                "port": assigned,
                "requestedPort": requested,
                "host": host,
                "protocol": protocol,
                "envFile": str(env_path) if env_path else None,
                "assignmentReason": assignment_reason,
            }
        )

    if not dry_run:
        _write_json(write_config, resolved)
        save_reserved_ports(str(reservation_file), reserved_ports)

    return {
        "valid": True,
        "mode": "servicewright-reconcile",
        "projectName": project,
        "sourceConfig": str(source),
        "resolvedConfig": str(Path(write_config).resolve()),
        "reservedPortsFile": str(reservation_file.resolve()),
        "dryRun": dry_run,
        "serviceCount": len(results),
        "results": results,
        "collection": is_collection,
    }
