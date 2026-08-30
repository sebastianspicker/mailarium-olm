"""MCP tool modules for the Mailarium server.

Each module exports a ``register(mcp, deps)`` function that binds
its tools to the shared FastMCP instance.  The *deps* argument is a
``ToolDeps`` namespace providing singletons, helpers, and constants
so that tool modules never import from ``mcp_server`` directly
(which would create a circular dependency).

Registration is intentionally explicit so each module owns its tool names,
schemas, and implementation helpers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from .utils import ToolDepsProto


def register_all(mcp: FastMCP, deps: ToolDepsProto) -> None:
    """Register the general email-analysis tool surface."""
    # Keep package import lightweight: answer-context type annotations import
    # ``tools.utils`` without eagerly importing every handler and forming a
    # circular path back to the answer-context workflow.
    from . import (
        attachments,
        browse,
        data_quality,
        diagnostics,
        entities,
        evidence,
        mailbox,
        network,
        reporting,
        scan,
        search,
        temporal,
        threads,
        topics,
    )

    modules = [
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
        mailbox,
        diagnostics,
        attachments,
        scan,
    ]
    for module in modules:
        module.register(mcp, deps)
