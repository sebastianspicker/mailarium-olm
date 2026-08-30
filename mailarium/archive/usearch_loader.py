"""Load USearch with globally visible NumKong symbols on macOS."""

from __future__ import annotations

import importlib
import os
import sys
from types import ModuleType
from typing import Any


def import_usearch() -> ModuleType:
    """Import USearch after exposing NumKong symbols on macOS."""
    if sys.platform == "darwin":
        previous_flags = sys.getdlopenflags()
        try:
            sys.setdlopenflags(previous_flags | os.RTLD_GLOBAL)
            importlib.import_module("numkong")
        finally:
            sys.setdlopenflags(previous_flags)
    return importlib.import_module("usearch")


def import_index() -> Any:
    """Return the USearch Index class after preparing native dependencies."""
    import_usearch()
    return importlib.import_module("usearch.index").Index
