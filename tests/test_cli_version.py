"""CLI package metadata regression coverage."""

from pathlib import Path

from mailarium import __version__


def test_cli_version_matches_project_metadata() -> None:
    pyproject = (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")

    assert f'version = "{__version__}"' in pyproject
