"""Thread-local ownership of per-search diagnostic payloads."""

from __future__ import annotations

import threading
from typing import Any


class SearchDiagnostics:
    """Own the last search, query-expansion, and semantic-filter diagnostics.

    Each worker thread reads and writes its own payloads.  The payload most
    recently stored by any thread seeds a thread that has not stored one yet.
    Collaborators record into the live search payload in place, so a returned
    ``search_debug`` dict reflects every stage of the current search.
    """

    def __init__(self) -> None:
        """Start with empty diagnostics for the constructing thread."""
        self._local = threading.local()
        self._latest_search_debug: dict[str, Any] = {}
        self._latest_query_expansion: dict[str, Any] | None = None
        self._latest_semantic_filter_errors: list[dict[str, Any]] | None = None
        self.set_search_debug()

    @property
    def search_debug(self) -> dict[str, Any]:
        """Return the current thread's live diagnostics for its last search."""
        debug = getattr(self._local, "search_debug", None)
        if not isinstance(debug, dict):
            debug = dict(self._latest_search_debug)
            self._local.search_debug = debug
        return debug

    def set_search_debug(self, payload: dict[str, Any] | None = None) -> None:
        """Replace the current thread's search diagnostics."""
        debug = dict(payload or {})
        self._local.search_debug = debug
        self._latest_search_debug = debug

    def record_search_debug(self, key: str, value: Any) -> None:
        """Add one stage's diagnostics to the current thread's live search payload."""
        self.search_debug[key] = value

    @property
    def query_expansion(self) -> dict[str, Any]:
        """Return the current thread's query-expansion diagnostics."""
        debug = getattr(self._local, "query_expansion", None)
        if not isinstance(debug, dict):
            latest = self._latest_query_expansion
            debug = dict(latest) if isinstance(latest, dict) else {}
            self._local.query_expansion = debug
        return debug

    def set_query_expansion(self, payload: dict[str, Any] | None = None) -> None:
        """Replace the current thread's query-expansion diagnostics."""
        debug = dict(payload or {})
        self._local.query_expansion = debug
        self._latest_query_expansion = debug

    @property
    def semantic_filter_errors(self) -> list[dict[str, Any]]:
        """Return the semantic-filter errors accumulated by the current thread's search."""
        errors = getattr(self._local, "semantic_filter_errors", None)
        if not isinstance(errors, list):
            latest = self._latest_semantic_filter_errors
            errors = list(latest) if isinstance(latest, list) else []
            self._local.semantic_filter_errors = errors
        return errors

    def set_semantic_filter_errors(self, errors: list[dict[str, Any]] | None = None) -> None:
        """Replace the current thread's semantic-filter errors with a snapshot."""
        snapshot = [dict(error) for error in (errors or [])]
        self._local.semantic_filter_errors = snapshot
        self._latest_semantic_filter_errors = snapshot
