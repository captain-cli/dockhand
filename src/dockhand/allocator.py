"""Core port allocation workflow."""

from __future__ import annotations

import argparse
from typing import Any, Dict, Optional

from .db import default_db_config_from_env, get_db_reserved_port, list_db_reserved_port_values, update_database_setting
from .env_file import get_env_reserved_port, update_env_file
from .firewall import allow_firewall_port, require_admin_for_firewall
from .naming import default_config_dir, default_env_var_name
from .ports import first_available_port, port_is_available
from .reservations import (
    get_reserved_port,
    list_reserved_port_values,
    load_reserved_ports,
    reservation_key,
    reserve_port,
    save_reserved_ports,
)
from .validation import validate_args


def resolve_defaults(args: argparse.Namespace) -> argparse.Namespace:
    config_dir = default_config_dir(args.project_name)
    if not args.reserved_ports_file:
        args.reserved_ports_file = str(config_dir / "reserved-ports.json")
    if args.env_file is None and args.write_env:
        args.env_file = str(config_dir / ".env")
    return args


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
