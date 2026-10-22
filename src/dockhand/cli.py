"""Dockhand command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Callable

from . import __version__
from .allocator import allocate_single
from .constants import (
    DEFAULT_DB_APP_COLUMN,
    DEFAULT_DB_DESCRIPTION_COLUMN,
    DEFAULT_DB_MODIFIED_USERID_COLUMN,
    DEFAULT_DB_SETTING_COLUMN,
    DEFAULT_DB_TABLE,
    DEFAULT_DB_VALUE_COLUMN,
    DEFAULT_END_PORT,
    DEFAULT_START_PORT,
)
from .errors import PortAllocationError
from .init_config import init_manifest
from .manifest import run_batch, validate_batch_config
from .servicewright import reconcile_servicewright_config
from .output import fail


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    identity = parser.add_argument_group("identity")
    identity.add_argument("--project-name", default="dockhand", help="Project namespace used for defaults, firewall rule names, and reservation metadata.")
    identity.add_argument("--application-name", required=False, help="Application/service name requesting the port. Required unless --applications-file/--config is used.")
    identity.add_argument("--setting-name", default="port", help="Setting name for this port. Example: port, httpPort, socketPort.")
    identity.add_argument("--setting-description", default="Dynamically assigned service port")
    identity.add_argument("--applications-file", "--config", dest="applications_file", default=None, help="JSON manifest containing multiple applications/services to allocate ports for.")

    identity.add_argument("--canonical-project", action="store_true", help="Resolve the dockhand section from a Captain project manifest. Use --config PROJECT_DIR or PROJECT_DIR/manifest.json.")

    port = parser.add_argument_group("port selection")
    port.add_argument("--start-port", type=int, default=DEFAULT_START_PORT)
    port.add_argument("--end-port", type=int, default=DEFAULT_END_PORT)
    port.add_argument("--host", default="0.0.0.0")
    port.add_argument("--protocol", choices=["tcp", "udp"], default="tcp")

    files = parser.add_argument_group("files")
    files.add_argument("--env-file", default=None, help="Optional .env file to read an existing reservation from.")
    files.add_argument("--env-var", default=None, help="Explicit env variable name for this setting. Defaults to PROJECT_APPLICATION_SETTING.")
    files.add_argument("--reserved-ports-file", default=None, help="JSON reservation file. Defaults to the project config directory.")
    files.add_argument("--write-env", action="store_true", help="Write/update the selected port in --env-file.")

    db = parser.add_argument_group("database optional")
    db.add_argument("--enable-db", action="store_true", help="Read/write reservations from MySQL/MariaDB.")
    db.add_argument("--db-host", default=None)
    db.add_argument("--db-user", default=None)
    db.add_argument("--db-password", default=None)
    db.add_argument("--db-name", default=None)
    db.add_argument("--db-port", type=int, default=None)
    db.add_argument("--db-table", default=DEFAULT_DB_TABLE)
    db.add_argument("--db-application-column", default=DEFAULT_DB_APP_COLUMN)
    db.add_argument("--db-setting-column", default=DEFAULT_DB_SETTING_COLUMN)
    db.add_argument("--db-value-column", default=DEFAULT_DB_VALUE_COLUMN)
    db.add_argument("--db-description-column", default=DEFAULT_DB_DESCRIPTION_COLUMN)
    db.add_argument("--db-modified-userid-column", default=DEFAULT_DB_MODIFIED_USERID_COLUMN)
    db.add_argument("--modified-userid", type=int, default=0)
    db.add_argument("--db-skip-write", action="store_true", help="Read from DB but do not write the selected port back.")

    firewall = parser.add_argument_group("firewall optional")
    firewall.add_argument("--open-firewall", action="store_true", help="Open the selected port in UFW or Windows Firewall.")
    firewall.add_argument("--firewall-comment", default=None)
    firewall.add_argument("--require-admin-for-firewall", action="store_true", help="Fail when --open-firewall is used without admin/root permissions.")

    output = parser.add_argument_group("output")
    output.add_argument("--json", action="store_true", help="Print JSON output instead of plain text.")
    output.add_argument("--quiet", action="store_true", help="Suppress warnings. The selected port is still printed.")
    output.add_argument("--print-env", action="store_true", help="Print env assignments for selected ports instead of the default text output.")


def build_legacy_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dockhand",
        description="Find an available port, reusing DB/env/file reservations before allocating a new one.",
    )
    parser.add_argument("--version", action="version", version=f"dockhand {__version__}")
    add_common_arguments(parser)
    return parser


def add_init_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output", default="manifest/dockhand.json", help="Path to write the starter Dockhand manifest.")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing manifest.")
    parser.add_argument("--project-name", default=None, help="Project name to place in the manifest. Defaults to the current directory name.")
    parser.add_argument("--application-name", default="app", help="Starter application/service name.")
    parser.add_argument("--setting-name", default="port", help="Starter setting name.")
    parser.add_argument("--setting-description", default="Application HTTP port")
    parser.add_argument("--start-port", type=int, default=41000)
    parser.add_argument("--end-port", type=int, default=41999)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--protocol", choices=["tcp", "udp"], default="tcp")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--reserved-ports-file", default="config/reserved-ports.json")
    parser.add_argument("--write-env", action="store_true", default=True)
    parser.add_argument("--json", action="store_true")



def add_servicewright_reconcile_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", required=True, help="Path to servicewright.json or a multi-service Servicewright config.")
    parser.add_argument(
        "--write-config",
        default=".captain/runtime/servicewright.resolved.json",
        help="Path for the resolved Servicewright config written after port reconciliation.",
    )
    parser.add_argument(
        "--write-env",
        default=".captain/runtime/environment",
        help="Directory for generated per-service env files. Use an empty value to use each service environmentFile path only.",
    )
    parser.add_argument("--root", default=None, help="Project root used to resolve relative paths. Defaults to the config directory.")
    parser.add_argument("--reserved-ports-file", default=None, help="Dockhand reservation file. Defaults to .captain/runtime/dockhand-reserved-ports.json under --root.")
    parser.add_argument("--project-name", default=None, help="Reservation project namespace. Defaults to config projectName/project or root folder name.")
    parser.add_argument("--start-port", type=int, default=DEFAULT_START_PORT, help="Default start port when a service runtime omits portRange.")
    parser.add_argument("--end-port", type=int, default=DEFAULT_END_PORT, help="Default end port when a service runtime omits portRange.")
    parser.add_argument("--protocol", choices=["tcp", "udp"], default="tcp")
    parser.add_argument("--dry-run", action="store_true", help="Preview reconciliation without writing config, env, or reservations.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")

def build_ports_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dockhand")
    parser.add_argument("--version", action="version", version=f"dockhand {__version__}")
    subparsers = parser.add_subparsers(dest="resource")

    init_parser = subparsers.add_parser("init", help="Create a starter Dockhand manifest.")
    add_init_arguments(init_parser)
    init_parser.set_defaults(handler=handle_init)

    servicewright = subparsers.add_parser("servicewright", help="Reconcile Servicewright runtime config.")
    servicewright_commands = servicewright.add_subparsers(dest="servicewright_command", required=True)

    reconcile_parser = servicewright_commands.add_parser("reconcile", help="Honor safe Servicewright ports, reassign conflicts, and write resolved runtime config.")
    add_servicewright_reconcile_arguments(reconcile_parser)
    reconcile_parser.set_defaults(handler=handle_servicewright_reconcile)

    ports = subparsers.add_parser("ports", help="Manage service port reservations.")
    port_commands = ports.add_subparsers(dest="ports_command", required=True)

    apply_parser = port_commands.add_parser("apply", help="Allocate/reuse ports and write requested outputs.")
    add_common_arguments(apply_parser)
    apply_parser.set_defaults(handler=handle_apply)

    plan_parser = port_commands.add_parser("plan", help="Preview allocations without writing files, DB settings, or firewall rules.")
    add_common_arguments(plan_parser)
    plan_parser.set_defaults(handler=handle_plan)

    validate_parser = port_commands.add_parser("validate", help="Validate a Dockhand manifest or single allocation arguments.")
    add_common_arguments(validate_parser)
    validate_parser.set_defaults(handler=handle_validate)

    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] in (["ports"], ["init"], ["servicewright"]) or argv[:1] == ["--version"]:
        return build_ports_parser().parse_args(argv)
    args = build_legacy_parser().parse_args(argv)
    args.handler = handle_apply
    args.legacy = True
    return args


def result_items(results: list[dict] | dict) -> list[dict]:
    return results if isinstance(results, list) else [results]


def print_env_results(results: list[dict] | dict) -> None:
    for result in result_items(results):
        print(f"{result['envVar']}={result['port']}")


def print_apply_results(args: argparse.Namespace, results: list[dict] | dict) -> None:
    if getattr(args, "print_env", False):
        print_env_results(results)
        return

    if args.json:
        if isinstance(results, list):
            print(json.dumps({"results": results}, indent=2, sort_keys=True))
        else:
            print(json.dumps(results, indent=2, sort_keys=True))
        return

    if isinstance(results, list):
        for result in results:
            print(f"{result['applicationName']}:{result['settingName']}={result['port']}")
    else:
        print(results["port"])


def run_apply(args: argparse.Namespace) -> list[dict] | dict:
    args.dry_run = bool(getattr(args, "dry_run", False))
    if args.applications_file:
        return run_batch(args)
    return allocate_single(args)


def handle_apply(args: argparse.Namespace) -> None:
    results = run_apply(args)
    print_apply_results(args, results)


def handle_plan(args: argparse.Namespace) -> None:
    args.dry_run = True
    results = run_apply(args)
    print_apply_results(args, results)


def handle_validate(args: argparse.Namespace) -> None:
    if args.applications_file:
        summary = validate_batch_config(args)
    else:
        args.dry_run = True
        allocate_single(args)
        summary = {"valid": True, "mode": "single", "applicationCount": 1}

    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print("OK")


def handle_init(args: argparse.Namespace) -> None:
    result = init_manifest(args)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"Created {result['created']}")


def handle_servicewright_reconcile(args: argparse.Namespace) -> None:
    write_env = args.write_env if args.write_env else None
    result = reconcile_servicewright_config(
        config_path=args.config,
        write_config=args.write_config,
        write_env=write_env,
        root=args.root,
        reserved_ports_file=args.reserved_ports_file,
        project_name=args.project_name,
        default_start_port=args.start_port,
        default_end_port=args.end_port,
        protocol=args.protocol,
        dry_run=args.dry_run,
    )
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    action = "Planned" if args.dry_run else "Resolved"
    print(f"{action} {result['serviceCount']} Servicewright service(s)")
    for item in result["results"]:
        requested = item.get("requestedPort")
        suffix = f" (requested {requested})" if requested and requested != item["port"] else ""
        print(f"{item['serviceName']}={item['port']}{suffix} - {item['assignmentReason']}")


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        handler: Callable[[argparse.Namespace], None] = args.handler
        handler(args)
    except PortAllocationError as exc:
        fail(str(exc))


if __name__ == "__main__":
    main()
