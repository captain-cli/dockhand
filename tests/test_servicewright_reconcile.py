from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "dockhand.cli", *args],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=True,
    )


def write_servicewright_config(tmp_path: Path, port: int = 45400) -> Path:
    config = tmp_path / "servicewright.json"
    config.write_text(
        json.dumps(
            {
                "projectName": "sw-project",
                "services": [
                    {
                        "name": "auth-api",
                        "description": "Auth API",
                        "type": "system",
                        "environmentFile": ".captain/runtime/environment/auth-api.env",
                        "runtime": {"host": "127.0.0.1", "port": port, "portRange": [45400, 45410]},
                    },
                    {
                        "name": "media-api",
                        "description": "Media API",
                        "type": "system",
                        "environmentFile": ".captain/runtime/environment/media-api.env",
                        "runtime": {"host": "127.0.0.1", "portRange": [45400, 45410]},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return config


def test_servicewright_reconcile_writes_resolved_config_and_env(tmp_path: Path) -> None:
    config = write_servicewright_config(tmp_path)
    resolved = tmp_path / ".captain/runtime/servicewright.resolved.json"
    env_dir = tmp_path / ".captain/runtime/environment"
    reserved = tmp_path / ".captain/runtime/dockhand-reserved-ports.json"

    result = run_cli(
        "servicewright",
        "reconcile",
        "--config",
        str(config),
        "--root",
        str(tmp_path),
        "--write-config",
        str(resolved),
        "--write-env",
        str(env_dir),
        "--reserved-ports-file",
        str(reserved),
        "--json",
    )

    payload = json.loads(result.stdout)
    assert payload["serviceCount"] == 2
    assert resolved.exists()
    assert (env_dir / "auth-api.env").exists()
    assert "PORT=45400" in (env_dir / "auth-api.env").read_text(encoding="utf-8")
    assert "PORT=45401" in (env_dir / "media-api.env").read_text(encoding="utf-8")

    resolved_payload = json.loads(resolved.read_text(encoding="utf-8"))
    services = {item["name"]: item for item in resolved_payload["services"]}
    assert services["auth-api"]["runtime"]["port"] == 45400
    assert services["media-api"]["runtime"]["port"] == 45401


def test_servicewright_reconcile_reassigns_unowned_busy_requested_port(tmp_path: Path) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    busy_port = sock.getsockname()[1]
    try:
        config = write_servicewright_config(tmp_path, port=busy_port)
        resolved = tmp_path / "resolved.json"
        result = run_cli(
            "servicewright",
            "reconcile",
            "--config",
            str(config),
            "--root",
            str(tmp_path),
            "--write-config",
            str(resolved),
            "--write-env",
            str(tmp_path / "env"),
            "--start-port",
            str(busy_port),
            "--end-port",
            str(busy_port + 10),
            "--json",
        )
    finally:
        sock.close()

    payload = json.loads(result.stdout)
    auth = next(item for item in payload["results"] if item["serviceName"] == "auth-api")
    assert auth["requestedPort"] == busy_port
    assert auth["port"] != busy_port
    assert "unavailable" in auth["assignmentReason"]


def test_servicewright_reconcile_dry_run_does_not_write(tmp_path: Path) -> None:
    config = write_servicewright_config(tmp_path)
    resolved = tmp_path / "resolved.json"
    env_dir = tmp_path / "env"

    result = run_cli(
        "servicewright",
        "reconcile",
        "--config",
        str(config),
        "--write-config",
        str(resolved),
        "--write-env",
        str(env_dir),
        "--dry-run",
        "--json",
    )

    payload = json.loads(result.stdout)
    assert payload["dryRun"] is True
    assert not resolved.exists()
    assert not env_dir.exists()
