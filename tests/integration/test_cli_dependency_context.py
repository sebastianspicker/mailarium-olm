"""CLI composition uses invocation-scoped runtime dependencies."""

from __future__ import annotations

from types import SimpleNamespace
from typing import ClassVar

import pytest

import mailarium.cli as cli
from mailarium.interfaces.cli import cli_commands, cli_commands_mailbox


class _Runtime:
    """Small runtime double that records ownership at the composition boundary."""

    instances: ClassVar[list[_Runtime]] = []

    def __init__(self, **_kwargs) -> None:
        self.database = object()
        self.search = SimpleNamespace(email_db=self.database)
        self.mailbox = SimpleNamespace(db=self.database)
        self.close_count = 0
        self.instances.append(self)

    @property
    def archive_database(self):
        return self.database

    @property
    def search_engine(self):
        return self.search

    def mailbox_service(self):
        return self.mailbox

    def close(self) -> None:
        self.close_count += 1

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        self.close()


def test_cli_dependencies_are_per_invocation_and_share_runtime_archive(monkeypatch) -> None:
    """Representative command families receive only their owning runtime's services."""
    _Runtime.instances.clear()
    received = []
    monkeypatch.setattr(cli, "ApplicationRuntime", _Runtime)
    monkeypatch.setattr(cli, "_cmd_browse", lambda _args, dependencies: received.append(dependencies))
    monkeypatch.setattr(cli, "_cmd_analytics", lambda _args, dependencies: received.append(dependencies))

    cli.main(["browse"])
    cli.main(["analytics", "stats"])

    assert len(received) == 2
    assert len(_Runtime.instances) == 2
    for dependencies, runtime in zip(received, _Runtime.instances, strict=True):
        assert dependencies.archive_database is runtime.database
        assert dependencies.search_engine.email_db is dependencies.archive_database
        assert dependencies.mailbox_service.db is dependencies.archive_database
        assert runtime.close_count == 1
    assert received[0].archive_database is not received[1].archive_database
    assert not hasattr(cli_commands, "_CLI_ARCHIVE_DATABASE")
    assert not hasattr(cli_commands, "_CLI_SQLITE_PATH_OVERRIDE")
    assert not hasattr(cli_commands_mailbox, "mailbox_service_for_path")


def test_cli_rejects_missing_archive_before_constructing_services(monkeypatch, capsys: pytest.CaptureFixture[str]) -> None:
    """A DB-backed CLI command cannot implicitly create a blank SQLite archive."""

    class _MissingArchiveRuntime(_Runtime):
        @property
        def archive_database(self):
            return None

        @property
        def search_engine(self):
            raise AssertionError("search engine must not be constructed for a missing archive")

        def mailbox_service(self):
            raise AssertionError("mailbox service must not be constructed for a missing archive")

    monkeypatch.setattr(cli, "ApplicationRuntime", _MissingArchiveRuntime)

    with pytest.raises(SystemExit, match="1"):
        cli.main(["browse"])

    assert "SQLite database not found" in capsys.readouterr().out
