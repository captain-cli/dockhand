import json
import subprocess
import sys
from pathlib import Path


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "dockhand.cli", *args],
        text=True,
        capture_output=True,
        check=True,
    )


def test_single_allocation_json(tmp_path):
    reserved = tmp_path / "reserved.json"
    result = run_cli(
        "--project-name", "test-project",
        "--application-name", "api",
        "--setting-name", "port",
        "--start-port", "45100",
        "--end-port", "45110",
        "--reserved-ports-file", str(reserved),
        "--json",
    )
    payload = json.loads(result.stdout)
    assert payload["applicationName"] == "api"
    assert 45100 <= payload["port"] <= 45110
    assert reserved.exists()


def test_batch_manifest(tmp_path):
    reserved = tmp_path / "reserved.json"
    env_file = tmp_path / ".env"
    manifest = tmp_path / "dockhand.json"
    manifest.write_text(json.dumps({
        "projectName": "batch-project",
        "defaults": {
            "startPort": 45200,
            "endPort": 45210,
            "reservedPortsFile": str(reserved),
            "envFile": str(env_file),
            "writeEnv": True
        },
        "applications": [
            {"applicationName": "api", "settingName": "port"},
            {"applicationName": "worker", "settingName": "socketPort", "envVar": "WORKER_SOCKET_PORT"}
        ]
    }))
    result = run_cli("--applications-file", str(manifest), "--json")
    payload = json.loads(result.stdout)
    assert len(payload["results"]) == 2
    assert "WORKER_SOCKET_PORT" in env_file.read_text()
