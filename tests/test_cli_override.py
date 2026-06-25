from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_batch_cli_paths_override_manifest_defaults(tmp_path: Path) -> None:
    manifest = tmp_path / "apps.json"
    reserved = tmp_path / "reserved.json"
    env_file = tmp_path / "batch.env"

    manifest.write_text(
        json.dumps(
            {
                "projectName": "override-project",
                "defaults": {
                    "startPort": 45100,
                    "endPort": 45110,
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

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "dockhand.cli",
            "--applications-file",
            str(manifest),
            "--reserved-ports-file",
            str(reserved),
            "--env-file",
            str(env_file),
            "--write-env",
            "--json",
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert all(item["reservedPortsFile"] == str(reserved) for item in payload["results"])
    assert all(item["envFile"] == str(env_file) for item in payload["results"])
    assert reserved.exists()
    assert env_file.exists()
    assert not (tmp_path / "manifest-reserved.json").exists()
    assert not (tmp_path / "manifest.env").exists()
