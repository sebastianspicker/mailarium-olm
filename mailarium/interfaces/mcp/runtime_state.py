"""Runtime generations, leases, and path overrides owned by one registered MCP server."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import Any

from mailarium.interfaces.runtime import ApplicationRuntime
from mailarium.platform.repo_paths import normalize_local_path, validate_runtime_path
from mailarium.platform.settings import get_settings


class McpRuntimeState:
    """Own one registered MCP server's runtime generation and path overrides.

    Offloaded tool work holds a lease for its complete blocking call.  A reset
    or path change therefore waits until the old generation is no longer in
    use before closing its resources.
    """

    def __init__(
        self,
        *,
        vector_index_path: str | None = None,
        sqlite_path: str | None = None,
        runtime_factory: Callable[..., ApplicationRuntime] = ApplicationRuntime,
    ) -> None:
        self._condition = threading.Condition(threading.RLock())
        self._runtime_factory = runtime_factory
        self._vector_index_path = self._validated_override(vector_index_path, field_name="vector_index_path")
        self._sqlite_path = self._validated_override(sqlite_path, field_name="sqlite_path")
        self._runtime: ApplicationRuntime | None = None
        self._in_flight_leases = 0
        self._lease_local = threading.local()
        self._reset_pending = False
        self._closed = False

    @staticmethod
    def _validated_override(path: str | None, *, field_name: str) -> str | None:
        if path is None:
            return None
        return str(validate_runtime_path(path, field_name=field_name))

    def resolved_runtime_paths(self) -> tuple[str, str]:
        """Return active paths after applying this server's local overrides."""
        with self._condition:
            self._ensure_open()
            return self._resolved_runtime_paths_locked()

    def get_application_runtime(self) -> ApplicationRuntime:
        """Return the one runtime identity for the active generation."""
        with self._condition:
            self._ensure_open()
            if self._runtime is None:
                vector_index_path, sqlite_path = self._resolved_runtime_paths_locked()
                self._runtime = self._runtime_factory(
                    vector_index_path=vector_index_path,
                    sqlite_path=sqlite_path,
                )
            return self._runtime

    def get_retriever(self) -> Any:
        """Return the active generation's shared search engine."""
        return self.get_application_runtime().search_engine

    def get_archive_database(self) -> Any:
        """Return the active generation's archive database when it exists."""
        return self.get_application_runtime().archive_database

    def get_mailbox_service(self) -> Any:
        """Return the active generation's proposal-gated mailbox service."""
        return self.get_application_runtime().mailbox_service()

    @property
    def in_flight_leases(self) -> int:
        """Expose the current lease count for lifecycle diagnostics and tests."""
        with self._condition:
            return self._in_flight_leases

    @contextmanager
    def lease(self) -> Generator:
        """Keep the active generation open for one blocking operation."""
        with self._condition:
            self._ensure_open()
            self._in_flight_leases += 1
        self._lease_local.depth = getattr(self._lease_local, "depth", 0) + 1
        try:
            yield
        finally:
            self._lease_local.depth -= 1
            runtime: ApplicationRuntime | None = None
            with self._condition:
                self._in_flight_leases -= 1
                if self._in_flight_leases == 0 and self._reset_pending:
                    self._reset_pending = False
                    runtime = self._runtime
                    self._runtime = None
                self._condition.notify_all()
            self._close_runtime(runtime)

    async def offload(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Run blocking MCP work in a leased worker thread."""

        def _run() -> Any:
            with self.lease():
                return fn(*args, **kwargs)

        return await asyncio.to_thread(_run)

    def set_archive_paths(
        self,
        *,
        vector_index_path: str | None = None,
        sqlite_path: str | None = None,
    ) -> bool:
        """Set validated overrides and replace the runtime after leases drain."""
        vector_override = self._validated_override(vector_index_path, field_name="vector_index_path")
        sqlite_override = self._validated_override(sqlite_path, field_name="sqlite_path")
        with self._condition:
            self._ensure_open()
            next_vector = self._vector_index_path if vector_index_path is None else vector_override
            next_sqlite = self._sqlite_path if sqlite_path is None else sqlite_override
            if next_vector == self._vector_index_path and next_sqlite == self._sqlite_path:
                return False
            runtime = self._detach_runtime_after_leases_locked()
            self._vector_index_path = next_vector
            self._sqlite_path = next_sqlite
        self._close_runtime(runtime)
        return True

    def reset_runtime_clients(self) -> None:
        """Discard the active runtime only after all offloaded calls complete."""
        with self._condition:
            self._ensure_open()
            if getattr(self._lease_local, "depth", 0):
                self._reset_pending = True
                return
            runtime = self._detach_runtime_after_leases_locked()
        self._close_runtime(runtime)

    def close(self) -> None:
        """Close this server state once; later calls are harmless."""
        with self._condition:
            if self._closed:
                return
            runtime = self._detach_runtime_after_leases_locked()
            self._closed = True
        self._close_runtime(runtime)

    def _resolved_runtime_paths_locked(self) -> tuple[str, str]:
        settings = get_settings()
        vector_index_path = self._vector_index_path or settings.vector_index_path
        sqlite_path = self._sqlite_path or settings.sqlite_path
        return (
            str(normalize_local_path(vector_index_path, field_name="vector_index_path")),
            str(normalize_local_path(sqlite_path, field_name="sqlite_path")),
        )

    def _detach_runtime_after_leases_locked(self) -> ApplicationRuntime | None:
        while self._in_flight_leases:
            self._condition.wait()
        runtime = self._runtime
        self._runtime = None
        return runtime

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("MCP runtime state is closed")

    @staticmethod
    def _close_runtime(runtime: ApplicationRuntime | None) -> None:
        if runtime is not None:
            runtime.close()
