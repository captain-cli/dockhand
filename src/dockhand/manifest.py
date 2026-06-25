"""Batch manifest loading and merge behavior."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List

from .allocator import allocate_single
from .output import fail


MANIFEST_KEY_MAP = {
    "projectName": "project_name",
    "applicationName": "application_name",
    "settingName": "setting_name",
    "settingDescription": "setting_description",
    "startPort": "start_port",
    "endPort": "end_port",
    "reservedPortsFile": "reserved_ports_file",
    "envFile": "env_file",
    "envVar": "env_var",
    "writeEnv": "write_env",
    "enableDb": "enable_db",
    "dbHost": "db_host",
    "dbUser": "db_user",
    "dbPassword": "db_password",
    "dbName": "db_name",
    "dbPort": "db_port",
    "dbTable": "db_table",
    "dbApplicationColumn": "db_application_column",
    "dbSettingColumn": "db_setting_column",
    "dbValueColumn": "db_value_column",
    "dbDescriptionColumn": "db_description_column",
    "dbModifiedUseridColumn": "db_modified_userid_column",
    "modifiedUserid": "modified_userid",
    "dbSkipWrite": "db_skip_write",
    "openFirewall": "open_firewall",
    "firewallComment": "firewall_comment",
    "requireAdminForFirewall": "require_admin_for_firewall",
}

CLI_OPTION_DESTS = {
    "--project-name": "project_name",
    "--application-name": "application_name",
    "--setting-name": "setting_name",
    "--setting-description": "setting_description",
    "--start-port": "start_port",
    "--end-port": "end_port",
    "--host": "host",
    "--protocol": "protocol",
    "--env-file": "env_file",
    "--env-var": "env_var",
    "--reserved-ports-file": "reserved_ports_file",
    "--write-env": "write_env",
    "--enable-db": "enable_db",
    "--db-host": "db_host",
    "--db-user": "db_user",
    "--db-password": "db_password",
    "--db-name": "db_name",
    "--db-port": "db_port",
    "--db-table": "db_table",
    "--db-application-column": "db_application_column",
    "--db-setting-column": "db_setting_column",
    "--db-value-column": "db_value_column",
    "--db-description-column": "db_description_column",
    "--db-modified-userid-column": "db_modified_userid_column",
    "--modified-userid": "modified_userid",
    "--db-skip-write": "db_skip_write",
    "--open-firewall": "open_firewall",
    "--firewall-comment": "firewall_comment",
    "--require-admin-for-firewall": "require_admin_for_firewall",
    "--json": "json",
    "--quiet": "quiet",
}


def normalize_manifest_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for key, value in data.items():
        normalized[MANIFEST_KEY_MAP.get(key, key)] = value
    return normalized


def load_applications_manifest(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        fail("Applications manifest must be a JSON object")
    if "applications" not in data or not isinstance(data["applications"], list):
        fail("Applications manifest must contain an applications array")
    return data


def get_explicit_cli_overrides(args: argparse.Namespace) -> Dict[str, Any]:
    """Return only options the user explicitly supplied on the CLI.

    In batch mode the precedence is:
      argparse defaults < manifest top-level < manifest defaults < app entry < explicit CLI flags
    """
    explicit: Dict[str, Any] = {}
    argv = sys.argv[1:]
    for token in argv:
        option = token.split("=", 1)[0] if token.startswith("--") else token
        dest = CLI_OPTION_DESTS.get(option)
        if not dest or dest in {"json", "quiet"}:
            continue
        explicit[dest] = getattr(args, dest)
    explicit.pop("applications_file", None)
    return explicit


def args_with_overrides(base_args: argparse.Namespace, overrides: Dict[str, Any]) -> argparse.Namespace:
    merged = vars(base_args).copy()
    merged.update(normalize_manifest_dict(overrides))
    return argparse.Namespace(**merged)


def run_batch(base_args: argparse.Namespace) -> List[Dict[str, Any]]:
    manifest = load_applications_manifest(base_args.applications_file)
    top_level = normalize_manifest_dict({k: v for k, v in manifest.items() if k != "applications" and k != "defaults"})
    defaults = normalize_manifest_dict(manifest.get("defaults", {}) or {})
    if not isinstance(defaults, dict):
        fail("Manifest defaults must be an object")

    explicit_cli = get_explicit_cli_overrides(base_args)

    results: List[Dict[str, Any]] = []
    for entry in manifest["applications"]:
        if not isinstance(entry, dict):
            fail("Each applications entry must be an object")
        merged: Dict[str, Any] = {}
        merged.update(top_level)
        merged.update(defaults)
        merged.update(normalize_manifest_dict(entry))
        merged.update(explicit_cli)
        single_args = args_with_overrides(base_args, merged)
        single_args.applications_file = None
        results.append(allocate_single(single_args))
    return results


def validate_batch_config(base_args: argparse.Namespace) -> Dict[str, Any]:
    """Validate a batch manifest and merged application arguments without writing outputs."""
    manifest = load_applications_manifest(base_args.applications_file)
    top_level = normalize_manifest_dict({k: v for k, v in manifest.items() if k != "applications" and k != "defaults"})
    defaults = normalize_manifest_dict(manifest.get("defaults", {}) or {})
    if not isinstance(defaults, dict):
        fail("Manifest defaults must be an object")

    explicit_cli = get_explicit_cli_overrides(base_args)
    application_count = 0
    for entry in manifest["applications"]:
        if not isinstance(entry, dict):
            fail("Each applications entry must be an object")
        merged: Dict[str, Any] = {}
        merged.update(top_level)
        merged.update(defaults)
        merged.update(normalize_manifest_dict(entry))
        merged.update(explicit_cli)
        single_args = args_with_overrides(base_args, merged)
        single_args.applications_file = None
        single_args.dry_run = True
        allocate_single(single_args)
        application_count += 1

    return {"valid": True, "mode": "batch", "applicationCount": application_count}
