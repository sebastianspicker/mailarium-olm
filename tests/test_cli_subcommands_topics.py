"""Reports an insufficient archive for topic modeling instead of attempting to fit an empty dataset."""

from __future__ import annotations

from mailarium.cli_commands_topics import run_topics_build_impl


class _EmptyConn:
    def execute(self, _query: str):
        return self

    def fetchall(self):
        return []


class _EmptyDb:
    conn = _EmptyConn()


def test_topics_build_reports_empty_runtime_without_fitting_models(capsys) -> None:
    run_topics_build_impl(_EmptyDb)

    out = capsys.readouterr().out
    assert "Not enough emails for topic/cluster analysis" in out
    assert "need at least 2" in out
