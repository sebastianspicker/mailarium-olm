"""Lifecycle contracts for MCP-owned application runtime state."""

from __future__ import annotations

import ast
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import mailarium.mcp_server as mcp_server
from mailarium.mcp_server import McpRuntimeState
from mailarium.runtime import ApplicationRuntime


class _Runtime:
    def __init__(self, **kwargs: str) -> None:
        self.kwargs = kwargs
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


def test_runtime_state_reuses_one_runtime_identity_and_close_is_idempotent() -> None:
    created: list[_Runtime] = []

    def factory(**kwargs: str) -> _Runtime:
        runtime = _Runtime(**kwargs)
        created.append(runtime)
        return runtime

    state = McpRuntimeState(runtime_factory=factory)  # type: ignore[arg-type]
    runtime = state.get_application_runtime()
    assert state.get_application_runtime() is runtime
    assert created == [runtime]

    state.close()
    state.close()

    assert runtime.close_calls == 1
    with pytest.raises(RuntimeError, match="closed"):
        state.get_application_runtime()


def test_reset_waits_for_the_offloaded_lease_before_closing_generation() -> None:
    created: list[_Runtime] = []
    started = threading.Event()
    release = threading.Event()
    reset_finished = threading.Event()

    def factory(**kwargs: str) -> _Runtime:
        runtime = _Runtime(**kwargs)
        created.append(runtime)
        return runtime

    async def exercise() -> None:
        state = McpRuntimeState(runtime_factory=factory)  # type: ignore[arg-type]
        original = state.get_application_runtime()

        def blocking_work() -> str:
            started.set()
            assert release.wait(timeout=2)
            return "complete"

        task = asyncio.create_task(state.offload(blocking_work))
        assert await asyncio.to_thread(started.wait, 2)
        assert state.in_flight_leases == 1

        def reset() -> None:
            state.reset_runtime_clients()
            reset_finished.set()

        reset_thread = threading.Thread(target=reset)
        reset_thread.start()
        await asyncio.sleep(0)
        assert original.close_calls == 0
        assert not reset_finished.is_set()

        release.set()
        assert await task == "complete"
        await asyncio.to_thread(reset_thread.join, 2)

        assert reset_finished.is_set()
        assert original.close_calls == 1
        replacement = state.get_application_runtime()
        assert replacement is not original
        state.close()

    asyncio.run(exercise())


def test_path_change_waits_for_a_lease_before_replacing_the_generation() -> None:
    created: list[_Runtime] = []
    started = threading.Event()
    release = threading.Event()
    mutation_finished = threading.Event()

    def factory(**kwargs: str) -> _Runtime:
        runtime = _Runtime(**kwargs)
        created.append(runtime)
        return runtime

    async def exercise() -> None:
        state = McpRuntimeState(runtime_factory=factory)  # type: ignore[arg-type]
        original = state.get_application_runtime()

        def blocking_work() -> None:
            started.set()
            assert release.wait(timeout=2)

        task = asyncio.create_task(state.offload(blocking_work))
        assert await asyncio.to_thread(started.wait, 2)

        def mutate_paths() -> None:
            assert state.set_archive_paths(vector_index_path="private/mcp-runtime-state-vectors")
            mutation_finished.set()

        mutation_thread = threading.Thread(target=mutate_paths)
        mutation_thread.start()
        await asyncio.sleep(0)
        assert original.close_calls == 0
        assert not mutation_finished.is_set()

        release.set()
        await task
        await asyncio.to_thread(mutation_thread.join, 2)

        assert mutation_finished.is_set()
        assert original.close_calls == 1
        replacement = state.get_application_runtime()
        assert replacement is not original
        assert replacement.kwargs["vector_index_path"].endswith("private/mcp-runtime-state-vectors")
        state.close()

    asyncio.run(exercise())


def test_reset_requested_by_offloaded_work_is_deferred_until_its_lease_exits() -> None:
    created: list[_Runtime] = []

    def factory(**kwargs: str) -> _Runtime:
        runtime = _Runtime(**kwargs)
        created.append(runtime)
        return runtime

    async def exercise() -> None:
        state = McpRuntimeState(runtime_factory=factory)  # type: ignore[arg-type]
        original = state.get_application_runtime()

        def reset_from_work() -> None:
            state.reset_runtime_clients()
            assert original.close_calls == 0

        await state.offload(reset_from_work)
        assert original.close_calls == 1
        state.close()

    asyncio.run(exercise())


def test_leased_concurrent_first_callers_share_one_application_runtime_generation(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MAILARIUM_RUNTIME_HOME", str(tmp_path / "runtime"))
    monkeypatch.delenv("MAILARIUM_ALLOWED_RUNTIME_ROOTS", raising=False)
    runtime = ApplicationRuntime(sqlite_path="archive/archive.db", vector_index_path="vectors")
    state = McpRuntimeState(runtime_factory=lambda **_kwargs: runtime)
    calls = ("database", "search", "mailbox") * 3
    barrier = threading.Barrier(len(calls))

    def first_call(kind: str):
        assert barrier.wait(timeout=5) >= 0
        leased_runtime = state.get_application_runtime()
        if kind == "database":
            return leased_runtime.open_archive_database()
        if kind == "search":
            return leased_runtime.search_engine
        return leased_runtime.mailbox_service(create_archive=True)

    async def exercise() -> None:
        asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(max_workers=len(calls)))
        results = await asyncio.gather(*(state.offload(first_call, kind) for kind in calls))
        database = next(result for kind, result in zip(calls, results, strict=True) if kind == "database")
        search = next(result for kind, result in zip(calls, results, strict=True) if kind == "search")
        mailbox = next(result for kind, result in zip(calls, results, strict=True) if kind == "mailbox")

        assert mailbox is not None
        assert all(result is database for kind, result in zip(calls, results, strict=True) if kind == "database")
        assert all(result is search for kind, result in zip(calls, results, strict=True) if kind == "search")
        assert all(result is mailbox for kind, result in zip(calls, results, strict=True) if kind == "mailbox")
        assert search.email_db is database
        assert mailbox.db is database
        state.close()

    asyncio.run(exercise())
    with pytest.raises(RuntimeError, match="closed"):
        state.get_application_runtime()


def test_mcp_server_keeps_only_the_instance_lock_as_mutable_module_state() -> None:
    source_path = Path(mcp_server.__file__)
    module = ast.parse(source_path.read_text(encoding="utf-8"))
    global_names = {name for node in ast.walk(module) if isinstance(node, ast.Global) for name in node.names}

    assert global_names == {"_lock_fd"}
    module_assignments = {
        target.id
        for node in module.body
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
        if isinstance(target, ast.Name)
    }
    assert (
        not {
            "_application_runtime",
            "_runtime_vector_index_path",
            "_runtime_sqlite_path",
        }
        & module_assignments
    )
    assert not any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "set_runtime_archive_paths"
        for node in module.body
    )
