"""OLM archive parsing and source-surface recovery."""

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..records import ParsedMessage
    from .parser import parse_olm

__all__ = ["ParsedMessage", "parse_olm"]


def __getattr__(name: str):
    """Defer the parser import until a caller requests the parser or its record type."""
    if name in __all__:
        module = import_module(".parser", __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
