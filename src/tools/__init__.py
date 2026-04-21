"""MCP tool modules for the email RAG server.

Each module exports a ``register(mcp, deps)`` function that binds
its tools to the shared FastMCP instance.  The *deps* argument is a
``ToolDeps`` namespace providing singletons, helpers, and constants
so that tool modules never import from ``mcp_server`` directly
(which would create a circular dependency).

Registration patterns (intentionally kept as-is — too simple to abstract):

- **Closure-based** (9 modules: browse, evidence, topics, temporal, entities,
  threads, network, reporting, attachments, data_quality): tools are defined
  inside ``register()`` and capture *deps* via closure.  Zero boilerplate.
- **Module-level _deps/_d()** (4 modules: search, diagnostics, scan): used
  when standalone async helpers outside ``register()`` need deps access.
  The 5-line ``_deps / _d() / register()`` pattern is repeated but trivial —
  a decorator or metaclass would add more complexity than it removes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from .utils import ToolDepsProto

from . import (
    attachments,
    browse,
    data_quality,
    diagnostics,
    entities,
    evidence,
    network,
    reporting,
    scan,
    search,
    temporal,
    threads,
    topics,
)

_MODULES = [
    search,
    network,
    temporal,
    entities,
    threads,
    topics,
    data_quality,
    reporting,
    browse,
    evidence,
    diagnostics,
    attachments,
    scan,
]


def register_all(mcp: FastMCP, deps: ToolDepsProto) -> None:
    """Register all tool modules with the MCP server."""
    for module in _MODULES:
        module.register(mcp, deps)
