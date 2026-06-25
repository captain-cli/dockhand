from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def run_cli(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "dockhand.cli", *args],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=check,
    )


def write_manifest(tmp_path: Path, applications: list[dict]) -> Path:
    manifest = tmp_path / "dockhand.json"
    manifest.write_text(
        json.dumps(
            {
                "projectName": "ready-project",
                "defaults": {
                    "startPort": 45400,
                    "endPort": 45410,
                    "reservedPortsFile": str(tmp_path / "reserved.json"),
                    "envFile": str(tmp_path / "app.env"),
                    "writeEnv": True,
                },
                "applications": applications,
            }
        ),
        encoding="utf-8",
    )
    return manifest


def test_version_command() -> None:
    result = run_cli("--version")
    assert result.stdout.strip().startswith("dockhand ")


def test_init_creates_manifest(tmp_path: Path) -> None:
    target = tmp_path / "manifest" / "dockhand.json"
    result = run_cli(
        "init",
        "--project-name",
        "sample-project",
        "--application-name",
        "api",
        "--output",
        str(target),
        "--json",
    )
    payload = json.loads(result.stdout)
    assert payload["created"] == str(target)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["projectName"] == "sample-project"
    assert data["applications"][0]["applicationName"] == "api"


def test_print_env_outputs_assignments(tmp_path: Path) -> None:
    manifest = write_manifest(
        tmp_path,
        [
            {"applicationName": "api", "settingName": "port"},
            {"applicationName": "worker", "settingName": "socketPort"},
        ],
    )
    result = run_cli("ports", "plan", "--config", str(manifest), "--print-env")
    lines = result.stdout.strip().splitlines()
    assert lines == ["READY_PROJECT_API_PORT=45400", "READY_PROJECT_WORKER_SOCKETPORT=45401"]


def test_env_file_has_no_blank_lines_between_generated_values(tmp_path: Path) -> None:
    manifest = write_manifest(
        tmp_path,
        [
            {"applicationName": "api", "settingName": "port"},
            {"applicationName": "worker", "settingName": "socketPort"},
        ],
    )
    env_file = tmp_path / "clean.env"
    run_cli("ports", "apply", "--config", str(manifest), "--env-file", str(env_file), "--write-env")
    assert env_file.read_text(encoding="utf-8") == "READY_PROJECT_API_PORT=45400\nREADY_PROJECT_WORKER_SOCKETPORT=45401\n"


def test_validate_rejects_duplicate_application_setting(tmp_path: Path) -> None:
    manifest = write_manifest(
        tmp_path,
        [
            {"applicationName": "api", "settingName": "port"},
            {"applicationName": "api", "settingName": "port"},
        ],
    )
    result = run_cli("ports", "validate", "--config", str(manifest), check=False)
    assert result.returncode != 0
    assert "Duplicate application/setting reservation" in result.stderr


def test_validate_rejects_duplicate_env_var(tmp_path: Path) -> None:
    manifest = write_manifest(
        tmp_path,
        [
            {"applicationName": "api", "settingName": "port", "envVar": "SHARED_PORT"},
            {"applicationName": "worker", "settingName": "port", "envVar": "SHARED_PORT"},
        ],
    )
    result = run_cli("ports", "validate", "--config", str(manifest), check=False)
    assert result.returncode != 0
    assert "Duplicate env var" in result.stderr
