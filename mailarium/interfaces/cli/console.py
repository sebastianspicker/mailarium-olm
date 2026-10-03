"""Shared terminal-output helpers for CLI command families."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def print_rich_or_plain(rich: Callable[[Any], Any], plain: Callable[[], Any]) -> None:
    """Try rich output, fall back to plain.

    Attempts to use rich formatting for output, falling back to plain text
    if the rich library is not available.

    Args:
        rich: Function to call with a Console for rich output.
        plain: Function to call for plain text output.
    """
    try:
        from rich.console import Console

        console = Console()
        rich(console)
    except ImportError:
        plain()
