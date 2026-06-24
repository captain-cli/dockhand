#!/usr/bin/env python3
"""
Generic Port Locator

Finds and reserves an available TCP/UDP port for any project.

Reservation priority:
  1. Existing DB setting, when --enable-db is used
  2. Existing env-file setting
  3. Existing JSON reservation-file setting
  4. First available unreserved port in the requested range

The script is intentionally project-agnostic:
  - No hardcoded project/application names
  - No hardcoded env variable mappings
  - Database support is optional
  - Firewall changes are optional
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

DEFAULT_START_PORT = 3000
DEFAULT_END_PORT = 65000
DEFAULT_DB_TABLE = "application_settings"
DEFAULT_DB_APP_COLUMN = "application_name"
DEFAULT_DB_SETTING_COLUMN = "application_setting_name"
DEFAULT_DB_VALUE_COLUMN = "application_setting_value"
DEFAULT_DB_DESCRIPTION_COLUMN = "application_setting_description"
DEFAULT_DB_MODIFIED_USERID_COLUMN = "last_modified_userid"


class PortAllocationError(Exception):
    """Raised when no suitable port can be found."""


def default_config_dir(project_name: str) -> Path:
    """Return a sane per-user config directory for the current OS."""
    safe_project = slugify(project_name) or "port-locator"

    if platform.system() == "Windows":
        root = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(root) / safe_project

    root = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(root) / safe_project


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9_.-]+", "-", value)
    value = re.sub(r"-+", "-", value)
    return value.strip("-._")


def env_key(value: str) -> str:
    """Convert arbitrary text to an env-friendly uppercase token."""
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", value.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned.upper()


def default_env_var_name(project_name: str, application_name: str, setting_name: str) -> str:
    parts = [env_key(project_name), env_key(application_name), env_key(setting_name)]
    parts = [part for part in parts if part]
    return "_".join(parts)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find an available port, reusing DB/env/file reservations before allocating a new one."
    )

    identity = parser.add_argument_group("identity")
    identity.add_argument("--project-name", default="port-locator", help="Project namespace used for defaults, firewall rule names, and reservation metadata.")
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


def fail(message: str, exit_code: int = 1) -> None:
    print(message, file=sys.stderr)
    sys.exit(exit_code)


def warn(args: argparse.Namespace, message: str) -> None:
    if not args.quiet:
        print(f"warning: {message}", file=sys.stderr)


def validate_identifier(value: str, label: str) -> None:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        fail(f"Invalid {label}: {value!r}. Use only letters, numbers, and underscores; do not start with a number.")


def validate_args(args: argparse.Namespace) -> None:
    if not (1 <= args.start_port <= 65535):
        fail(f"Invalid --start-port: {args.start_port}")
    if not (1 <= args.end_port <= 65535):
        fail(f"Invalid --end-port: {args.end_port}")
    if args.start_port > args.end_port:
        fail("--start-port cannot be greater than --end-port")

    if not args.applications_file and not args.application_name:
        fail("--application-name is required unless --applications-file is used")

    if args.enable_db:
        validate_identifier(args.db_table, "--db-table")
        validate_identifier(args.db_application_column, "--db-application-column")
        validate_identifier(args.db_setting_column, "--db-setting-column")
        validate_identifier(args.db_value_column, "--db-value-column")
        validate_identifier(args.db_description_column, "--db-description-column")
        validate_identifier(args.db_modified_userid_column, "--db-modified-userid-column")

    if args.write_env and not args.env_file:
        fail("--write-env requires --env-file")


def is_admin() -> bool:
    if platform.system() == "Windows":
        try:
            import ctypes  # type: ignore
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    return hasattr(os, "geteuid") and os.geteuid() == 0


def require_admin_for_firewall(args: argparse.Namespace) -> None:
    if args.open_firewall and args.require_admin_for_firewall and not is_admin():
        fail("Administrator/root privileges are required to open firewall ports.")


def require_ufw() -> Optional[str]:
    if platform.system() == "Windows":
        return None
    return shutil.which("ufw")


def is_ufw_active(ufw_path: str) -> bool:
    result = subprocess.run([ufw_path, "status"], capture_output=True, text=True, check=False)
    return "Status: active" in result.stdout


def ufw_rule_exists(ufw_path: str, port: int, protocol: str) -> bool:
    result = subprocess.run([ufw_path, "status", "numbered"], capture_output=True, text=True, check=False)
    return f"{port}/{protocol}" in result.stdout


def windows_rule_name(project_name: str, port: int, protocol: str) -> str:
    return f"{slugify(project_name) or 'port-locator'}-{port}-{protocol}"


def netsh_rule_exists(project_name: str, port: int, protocol: str) -> bool:
    result = subprocess.run(
        ["netsh", "advfirewall", "firewall", "show", "rule", f"name={windows_rule_name(project_name, port, protocol)}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def allow_windows_firewall_port(project_name: str, port: int, protocol: str) -> None:
    rule_name = windows_rule_name(project_name, port, protocol)
    if netsh_rule_exists(project_name, port, protocol):
        return
    result = subprocess.run(
        [
            "netsh", "advfirewall", "firewall", "add", "rule",
            f"name={rule_name}", "dir=in", "action=allow",
            f"protocol={protocol.upper()}", f"localport={port}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        fail(f"Failed to allow port through Windows Firewall: {result.stderr.strip()}")


def allow_firewall_port(args: argparse.Namespace, port: int) -> None:
    if not args.open_firewall:
        return

    if platform.system() == "Windows":
        allow_windows_firewall_port(args.project_name, port, args.protocol)
        return

    ufw_path = require_ufw()
    if not ufw_path:
        warn(args, "UFW was not found; skipping firewall update.")
        return
    if not is_ufw_active(ufw_path):
        warn(args, "UFW is not active; skipping firewall update.")
        return
    if ufw_rule_exists(ufw_path, port, args.protocol):
        return

    comment = args.firewall_comment or f"{args.project_name} dynamic port"
    result = subprocess.run(
        [ufw_path, "allow", f"{port}/{args.protocol}", "comment", comment],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        fail(f"Failed to allow port through UFW: {result.stderr.strip()}")


def parse_env_file(env_file: Optional[str]) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not env_file or not Path(env_file).exists():
        return values

    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def get_env_reserved_port(env_file: Optional[str], env_var_name: str) -> Optional[int]:
    raw = parse_env_file(env_file).get(env_var_name)
    if raw is None:
        raw = os.environ.get(env_var_name)
    if raw is None:
        return None
    try:
        value = int(str(raw))
    except (TypeError, ValueError):
        return None
    return value if 1 <= value <= 65535 else None


def update_env_file(env_file: str, env_var_name: str, port: int) -> None:
    path = Path(env_file)
    path.parent.mkdir(parents=True, exist_ok=True)

    lines: List[str] = []
    found = False
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()

    updated: List[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key, _ = stripped.split("=", 1)
            if key.strip() == env_var_name:
                updated.append(f"{env_var_name}={port}")
                found = True
                continue
        updated.append(line)

    if not found:
        if updated and updated[-1].strip():
            updated.append("")
        updated.append(f"{env_var_name}={port}")

    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text("\n".join(updated) + "\n", encoding="utf-8")
    os.replace(tmp_path, path)


def default_db_config_from_env(env_file: Optional[str], args: argparse.Namespace) -> Dict[str, str | int]:
    env = parse_env_file(env_file)

    def first(*names: str, default: Optional[str] = None) -> Optional[str]:
        for name in names:
            if getattr(args, name.lower().replace("db_", "db_"), None):
                return getattr(args, name.lower().replace("db_", "db_"))
        for name in names:
            if env.get(name):
                return env[name]
            if os.environ.get(name):
                return os.environ[name]
        return default

    # Accept generic names first, then legacy CRISPY_* names for backward compatibility.
    host = args.db_host or env.get("DB_HOST") or os.environ.get("DB_HOST") or env.get("CRISPY_DB_HOST") or os.environ.get("CRISPY_DB_HOST") or "127.0.0.1"
    user = args.db_user or env.get("DB_USER") or os.environ.get("DB_USER") or env.get("CRISPY_DB_USER") or os.environ.get("CRISPY_DB_USER") or "root"
    password = args.db_password if args.db_password is not None else env.get("DB_PASSWORD") or os.environ.get("DB_PASSWORD") or env.get("DB_PASS") or os.environ.get("DB_PASS") or env.get("CRISPY_DB_PASS") or os.environ.get("CRISPY_DB_PASS") or ""
    database = args.db_name or env.get("DB_NAME") or os.environ.get("DB_NAME")
    raw_port = args.db_port or env.get("DB_PORT") or os.environ.get("DB_PORT") or 3306

    if not database:
        fail("--enable-db requires --db-name or DB_NAME in the env/environment.")

    try:
        port = int(raw_port)
    except (TypeError, ValueError):
        fail(f"Invalid database port: {raw_port!r}")

    return {"host": host, "user": user, "password": password, "database": database, "port": port}


def connect_db(db_config: Dict[str, str | int]):
    try:
        import mysql.connector  # type: ignore
    except ImportError as exc:
        raise RuntimeError("mysql-connector-python is required when --enable-db is used.") from exc

    return mysql.connector.connect(
        host=db_config["host"],
        user=db_config["user"],
        password=db_config["password"],
        database=db_config["database"],
        port=db_config["port"],
    )


def load_reserved_ports(path: str) -> Dict[str, Dict[str, object]]:
    if not Path(path).exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_reserved_ports(path: str, data: Dict[str, Dict[str, object]]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    os.replace(tmp_path, path)


def reservation_key(project_name: str, application_name: str, setting_name: str) -> str:
    return f"{project_name}:{application_name}:{setting_name}"


def get_reserved_port(reserved_ports: Dict[str, Dict[str, object]], key: str, protocol: str) -> Optional[int]:
    entry = reserved_ports.get(key)
    if not isinstance(entry, dict) or entry.get("protocol") != protocol:
        return None
    port = entry.get("port")
    return port if isinstance(port, int) else None


def reserve_port(
    reserved_ports: Dict[str, Dict[str, object]],
    key: str,
    project_name: str,
    application_name: str,
    setting_name: str,
    port: int,
    protocol: str,
    description: str,
    env_var_name: str,
) -> None:
    reserved_ports[key] = {
        "project_name": project_name,
        "application_name": application_name,
        "setting_name": setting_name,
        "description": description,
        "port": port,
        "protocol": protocol,
        "env_var": env_var_name,
    }


def list_reserved_port_values(reserved_ports: Dict[str, Dict[str, object]], protocol: str, exclude_key: Optional[str] = None) -> List[int]:
    ports: List[int] = []
    for key, entry in reserved_ports.items():
        if exclude_key and key == exclude_key:
            continue
        if not isinstance(entry, dict) or entry.get("protocol") != protocol:
            continue
        port = entry.get("port")
        if isinstance(port, int):
            ports.append(port)
    return ports


def query_column(args: argparse.Namespace, column: str) -> str:
    validate_identifier(column, "database column")
    return f"`{column}`"


def get_db_reserved_port(db_config: Dict[str, str | int], args: argparse.Namespace) -> Optional[int]:
    try:
        conn = connect_db(db_config)
    except Exception:
        return None
    try:
        cursor = conn.cursor()
        sql = (
            f"SELECT {query_column(args, args.db_value_column)} "
            f"FROM `{args.db_table}` "
            f"WHERE {query_column(args, args.db_application_column)} = %s "
            f"AND {query_column(args, args.db_setting_column)} = %s "
            "LIMIT 1"
        )
        cursor.execute(sql, (args.application_name, args.setting_name))
        row = cursor.fetchone()
        if row and row[0] is not None:
            try:
                value = int(str(row[0]))
                return value if 1 <= value <= 65535 else None
            except (TypeError, ValueError):
                return None
        return None
    finally:
        conn.close()


def list_db_reserved_port_values(db_config: Dict[str, str | int], args: argparse.Namespace) -> List[int]:
    try:
        conn = connect_db(db_config)
    except Exception:
        return []
    try:
        cursor = conn.cursor()
        sql = (
            f"SELECT {query_column(args, args.db_value_column)} "
            f"FROM `{args.db_table}` "
            f"WHERE NOT ({query_column(args, args.db_application_column)} = %s "
            f"AND {query_column(args, args.db_setting_column)} = %s)"
        )
        cursor.execute(sql, (args.application_name, args.setting_name))
        ports: List[int] = []
        for (value,) in cursor.fetchall():
            try:
                port = int(str(value))
            except (TypeError, ValueError):
                continue
            if 1 <= port <= 65535:
                ports.append(port)
        return ports
    finally:
        conn.close()


def port_is_available(host: str, port: int, protocol: str) -> bool:
    sock_type = socket.SOCK_STREAM if protocol == "tcp" else socket.SOCK_DGRAM
    with closing(socket.socket(socket.AF_INET, sock_type)) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def first_available_port(start_port: int, end_port: int, host: str, protocol: str, blocked: Iterable[int]) -> int:
    blocked_set = set(blocked)
    for port in range(start_port, end_port + 1):
        if port in blocked_set:
            continue
        if port_is_available(host, port, protocol):
            return port
    raise PortAllocationError(f"No available {protocol.upper()} port found in range {start_port}-{end_port}")


def find_available_port(
    args: argparse.Namespace,
    reserved_ports: Dict[str, Dict[str, object]],
    db_config: Optional[Dict[str, str | int]],
    env_var_name: str,
    reservation: str,
) -> int:
    if args.enable_db and db_config:
        db_existing = get_db_reserved_port(db_config, args)
        if db_existing is not None and port_is_available(args.host, db_existing, args.protocol):
            return db_existing

    env_existing = get_env_reserved_port(args.env_file, env_var_name)
    if env_existing is not None and port_is_available(args.host, env_existing, args.protocol):
        return env_existing

    file_existing = get_reserved_port(reserved_ports, reservation, args.protocol)
    if file_existing is not None and port_is_available(args.host, file_existing, args.protocol):
        return file_existing

    blocked = set(list_reserved_port_values(reserved_ports, args.protocol, exclude_key=reservation))
    if args.enable_db and db_config:
        blocked.update(list_db_reserved_port_values(db_config, args))

    return first_available_port(args.start_port, args.end_port, args.host, args.protocol, blocked)


def update_database_setting(db_config: Dict[str, str | int], args: argparse.Namespace, setting_value: str) -> None:
    conn = connect_db(db_config)
    try:
        cursor = conn.cursor()
        sql = f"""
            INSERT INTO `{args.db_table}`
                ({query_column(args, args.db_application_column)},
                 {query_column(args, args.db_setting_column)},
                 {query_column(args, args.db_value_column)},
                 {query_column(args, args.db_description_column)},
                 {query_column(args, args.db_modified_userid_column)})
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                {query_column(args, args.db_value_column)} = VALUES({query_column(args, args.db_value_column)}),
                {query_column(args, args.db_description_column)} = VALUES({query_column(args, args.db_description_column)}),
                {query_column(args, args.db_modified_userid_column)} = VALUES({query_column(args, args.db_modified_userid_column)})
        """
        cursor.execute(
            sql,
            (
                args.application_name,
                args.setting_name,
                setting_value,
                args.setting_description,
                args.modified_userid,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def resolve_defaults(args: argparse.Namespace) -> argparse.Namespace:
    config_dir = default_config_dir(args.project_name)
    if not args.reserved_ports_file:
        args.reserved_ports_file = str(config_dir / "reserved-ports.json")
    if args.env_file is None and args.write_env:
        args.env_file = str(config_dir / ".env")
    return args



def allocate_single(args: argparse.Namespace) -> Dict[str, Any]:
    """Allocate one port and return a structured result."""
    args = resolve_defaults(args)
    validate_args(args)
    require_admin_for_firewall(args)

    env_var_name = args.env_var or default_env_var_name(args.project_name, args.application_name, args.setting_name)
    reservation = reservation_key(args.project_name, args.application_name, args.setting_name)
    reserved_ports = load_reserved_ports(args.reserved_ports_file)
    db_config = default_db_config_from_env(args.env_file, args) if args.enable_db else None

    port = find_available_port(args, reserved_ports, db_config, env_var_name, reservation)

    reserve_port(
        reserved_ports=reserved_ports,
        key=reservation,
        project_name=args.project_name,
        application_name=args.application_name,
        setting_name=args.setting_name,
        port=port,
        protocol=args.protocol,
        description=args.setting_description,
        env_var_name=env_var_name,
    )
    save_reserved_ports(args.reserved_ports_file, reserved_ports)

    if args.write_env and args.env_file:
        update_env_file(args.env_file, env_var_name, port)

    allow_firewall_port(args, port)

    if args.enable_db and db_config and not args.db_skip_write:
        update_database_setting(db_config, args, str(port))

    return {
        "projectName": args.project_name,
        "applicationName": args.application_name,
        "settingName": args.setting_name,
        "envVar": env_var_name,
        "port": port,
        "protocol": args.protocol,
        "host": args.host,
        "reservedPortsFile": args.reserved_ports_file,
        "envFile": args.env_file,
        "databaseEnabled": args.enable_db,
        "firewallOpened": args.open_firewall,
    }


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


def get_explicit_cli_overrides(args: argparse.Namespace) -> Dict[str, Any]:
    """Return only options the user explicitly supplied on the CLI.

    In batch mode the precedence should be:
      built-in argparse defaults < manifest top-level < manifest defaults < app entry < explicit CLI flags

    argparse does not tell us this directly, so we inspect sys.argv for known long flags.
    """
    explicit: Dict[str, Any] = {}
    argv = sys.argv[1:]
    for token in argv:
        option = token.split("=", 1)[0] if token.startswith("--") else token
        dest = CLI_OPTION_DESTS.get(option)
        if not dest or dest in {"json", "quiet"}:
            continue
        explicit[dest] = getattr(args, dest)
    # These control batch execution/output, not each per-app allocation.
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
