"""Optional firewall integration."""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
from typing import Optional

from .naming import slugify
from .output import fail, warn


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
    return f"{slugify(project_name) or 'dockhand'}-{port}-{protocol}"


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
