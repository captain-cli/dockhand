"""Starter manifest generation for Dockhand."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .output import fail


def default_init_manifest(args: argparse.Namespace) -> dict:
    project_name = args.project_name or Path.cwd().name or "my-project"
    return {
        "projectName": project_name,
        "defaults": {
            "startPort": args.start_port,
            "endPort": args.end_port,
            "host": args.host,
            "protocol": args.protocol,
            "envFile": args.env_file,
            "reservedPortsFile": args.reserved_ports_file,
            "writeEnv": bool(args.write_env),
        },
        "applications": [
            {
                "applicationName": args.application_name,
                "settingName": args.setting_name,
                "settingDescription": args.setting_description,
            }
        ],
    }


def init_manifest(args: argparse.Namespace) -> dict:
    output_path = Path(args.output)
    if output_path.exists() and not args.force:
        fail(f"Refusing to overwrite existing file: {output_path}. Use --force to replace it.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = default_init_manifest(args)
    output_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return {"created": str(output_path), "projectName": data["projectName"], "applicationCount": len(data["applications"])}
