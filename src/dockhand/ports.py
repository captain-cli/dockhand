"""Port probing and selection."""

from __future__ import annotations

import socket
from contextlib import closing
from typing import Iterable

from .errors import PortAllocationError


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
