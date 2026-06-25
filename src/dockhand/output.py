"""Console output helpers."""

from __future__ import annotations

import argparse
import sys


def fail(message: str, exit_code: int = 1) -> None:
    print(message, file=sys.stderr)
    sys.exit(exit_code)


def warn(args: argparse.Namespace, message: str) -> None:
    if not getattr(args, "quiet", False):
        print(f"warning: {message}", file=sys.stderr)
