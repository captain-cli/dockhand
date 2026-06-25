"""Argument validation."""

from __future__ import annotations

import argparse

from .naming import validate_identifier
from .output import fail


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
