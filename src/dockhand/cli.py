"""Dockhand command-line interface."""

from __future__ import annotations

import argparse
import json

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
from .manifest import run_batch
from .output import fail


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="dockhand",
        description="Find an available port, reusing DB/env/file reservations before allocating a new one.",
    )

    identity = parser.add_argument_group("identity")
    identity.add_argument("--project-name", default="dockhand", help="Project namespace used for defaults, firewall rule names, and reservation metadata.")
    identity.add_argument("--application-name", required=False, help="Application/service name requesting the port. Required unless --applications-file is used.")
    identity.add_argument("--setting-name", default="port", help="Setting name for this port. Example: port, httpPort, socketPort.")
    identity.add_argument("--setting-description", default="Dynamically assigned service port")
    identity.add_argument("--applications-file", default=None, help="JSON manifest containing multiple applications/services to allocate ports for.")

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
    output.add_argument("--json", action="store_true", help="Print JSON output instead of only the port.")
    output.add_argument("--quiet", action="store_true", help="Suppress warnings. The selected port is still printed.")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        if args.applications_file:
            results = run_batch(args)
            if args.json:
                print(json.dumps({"results": results}, indent=2, sort_keys=True))
            else:
                for result in results:
                    print(f"{result['applicationName']}:{result['settingName']}={result['port']}")
            return

        result = allocate_single(args)
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(result["port"])
    except PortAllocationError as exc:
        fail(str(exc))


if __name__ == "__main__":
    main()
