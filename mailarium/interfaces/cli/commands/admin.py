"""The ``admin`` command family: derived-index maintenance."""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mailarium.interfaces.cli.dependencies import CliDependencies


def run(args: argparse.Namespace, dependencies: CliDependencies) -> None:
    """Handle `admin` subcommand."""
    action = getattr(args, "admin_action", None)
    if action == "reset-index":
        if not getattr(args, "yes", False):
            print("Refusing to reset index without --yes.")
            sys.exit(2)
        dependencies.search_engine.reset_index()
        print("Index has been reset.")
    else:
        print("Usage: python -m mailarium.cli admin {reset-index}")
        sys.exit(2)
    sys.exit(0)
