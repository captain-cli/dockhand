from __future__ import annotations

import json
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


def write_manifest(tmp_path: Path) -> Path:
    manifest = tmp_path / "dockhand.json"
    manifest.write_text(
        json.dumps(
            {
                "projectName": "subcommand-project",
                "defaults": {
                    "startPort": 45300,
                    "endPort": 45310,
                    "reservedPortsFile": str(tmp_path / "manifest-reserved.json"),
                    "envFile": str(tmp_path / "manifest.env"),
                    "writeEnv": True,
                },
                "applications": [
                    {"applicationName": "api", "settingName": "port"},
                    {"applicationName": "worker", "settingName": "socketPort"},
                ],
            }
        ),
        encoding="utf-8",
    )
    return manifest


def test_ports_apply_writes_outputs(tmp_path: Path) -> None:
    manifest = write_manifest(tmp_path)
    reserved = tmp_path / "reserved.json"
    env_file = tmp_path / "batch.env"

    result = run_cli(
        "ports",
        "apply",
        "--config",
        str(manifest),
        "--reserved-ports-file",
        str(reserved),
        "--env-file",
        str(env_file),
        "--write-env",
        "--json",
    )

    payload = json.loads(result.stdout)
    assert len(payload["results"]) == 2
    assert reserved.exists()
    assert env_file.exists()
    assert all(item["dryRun"] is False for item in payload["results"])


def test_ports_plan_does_not_write_outputs(tmp_path: Path) -> None:
    manifest = write_manifest(tmp_path)
    reserved = tmp_path / "reserved.json"
    env_file = tmp_path / "batch.env"

    result = run_cli(
        "ports",
        "plan",
        "--config",
        str(manifest),
        "--reserved-ports-file",
        str(reserved),
        "--env-file",
        str(env_file),
        "--write-env",
        "--json",
    )

    payload = json.loads(result.stdout)
    assert len(payload["results"]) == 2
    assert not reserved.exists()
    assert not env_file.exists()
    assert all(item["dryRun"] is True for item in payload["results"])


def test_ports_validate_manifest(tmp_path: Path) -> None:
    manifest = write_manifest(tmp_path)
    result = run_cli("ports", "validate", "--config", str(manifest), "--json")
    payload = json.loads(result.stdout)
    assert payload == {"applicationCount": 2, "mode": "batch", "valid": True}


def test_legacy_batch_still_works(tmp_path: Path) -> None:
    manifest = write_manifest(tmp_path)
    result = run_cli("--applications-file", str(manifest), "--json")
    payload = json.loads(result.stdout)
    assert len(payload["results"]) == 2


def test_ports_plan_reserves_ports_in_memory(tmp_path: Path) -> None:
    manifest = write_manifest(tmp_path)
    reserved = tmp_path / "reserved.json"
    env_file = tmp_path / "batch.env"

    result = run_cli(
        "ports",
        "plan",
        "--config",
        str(manifest),
        "--reserved-ports-file",
        str(reserved),
        "--env-file",
        str(env_file),
        "--write-env",
        "--json",
    )

    payload = json.loads(result.stdout)
    ports = [item["port"] for item in payload["results"]]
    assert ports == [45300, 45301]
    assert not reserved.exists()
    assert not env_file.exists()
