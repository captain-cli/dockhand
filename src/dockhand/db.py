"""Optional MySQL/MariaDB reservation support."""

from __future__ import annotations

import argparse
import os
from typing import Dict, List, Optional

from .env_file import parse_env_file
from .naming import validate_identifier
from .output import fail


def default_db_config_from_env(env_file: Optional[str], args: argparse.Namespace) -> Dict[str, str | int]:
    env = parse_env_file(env_file)

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


def query_column(column: str) -> str:
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
            f"SELECT {query_column(args.db_value_column)} "
            f"FROM `{args.db_table}` "
            f"WHERE {query_column(args.db_application_column)} = %s "
            f"AND {query_column(args.db_setting_column)} = %s "
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
            f"SELECT {query_column(args.db_value_column)} "
            f"FROM `{args.db_table}` "
            f"WHERE NOT ({query_column(args.db_application_column)} = %s "
            f"AND {query_column(args.db_setting_column)} = %s)"
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


def update_database_setting(db_config: Dict[str, str | int], args: argparse.Namespace, setting_value: str) -> None:
    conn = connect_db(db_config)
    try:
        cursor = conn.cursor()
        sql = f"""
            INSERT INTO `{args.db_table}`
                ({query_column(args.db_application_column)},
                 {query_column(args.db_setting_column)},
                 {query_column(args.db_value_column)},
                 {query_column(args.db_description_column)},
                 {query_column(args.db_modified_userid_column)})
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                {query_column(args.db_value_column)} = VALUES({query_column(args.db_value_column)}),
                {query_column(args.db_description_column)} = VALUES({query_column(args.db_description_column)}),
                {query_column(args.db_modified_userid_column)} = VALUES({query_column(args.db_modified_userid_column)})
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
