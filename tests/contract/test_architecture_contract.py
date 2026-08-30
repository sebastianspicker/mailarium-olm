"""Tests for the exhaustive package-level architecture import gate."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

CHECKER_PATH = Path(__file__).resolve().parents[2] / "scripts" / "check_architecture.py"
SPEC = importlib.util.spec_from_file_location("check_architecture", CHECKER_PATH)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


def write_module(root: Path, relative_path: str, content: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_current_feature_graph_is_acyclic() -> None:
    root = Path(__file__).resolve().parents[2]

    assert checker.check(root) == []


def test_check_reports_forbidden_known_package_edge_with_exact_path_line_and_edge(tmp_path: Path) -> None:
    write_module(
        tmp_path,
        "mailarium/model/__init__.py",
        "from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    from mailarium.retrieval import retriever\n",
    )

    violations = checker.check(tmp_path)

    assert [item.render(tmp_path) for item in violations] == [
        "mailarium/model/__init__.py:4 -> mailarium.model -> mailarium.retrieval (model must not import retrieval)"
    ]


def test_check_allows_intentional_stdlib_and_third_party_imports(tmp_path: Path) -> None:
    write_module(tmp_path, "mailarium/model/__init__.py", "import json\nimport pydantic\n")

    assert checker.check(tmp_path) == []


def test_check_rejects_an_introduced_compatibility_package_cycle(tmp_path: Path) -> None:
    write_module(tmp_path, "mailarium/mailbox/__init__.py", "from mailarium.compatibility import bridge\n")
    write_module(tmp_path, "mailarium/compatibility/__init__.py", "from mailarium.mailbox import service\n")

    rendered = [item.render(tmp_path) for item in checker.check(tmp_path)]

    assert any("package cycle: compatibility -> mailbox -> compatibility" in item for item in rendered)


def test_check_rejects_unknown_architectural_packages(tmp_path: Path) -> None:
    write_module(tmp_path, "mailarium/model/service.py", "from mailarium.legacy import adapter\n")
    write_module(tmp_path, "mailarium/legacy/__init__.py", "")

    rendered = [item.render(tmp_path) for item in checker.check(tmp_path)]

    assert rendered == [
        "mailarium/legacy/__init__.py:1 -> mailarium.legacy -> mailarium.legacy (unknown architectural package: legacy)",
        "mailarium/model/service.py:1 -> mailarium.model.service -> mailarium.legacy (unknown root or package: legacy)",
    ]


def test_check_expands_root_package_import_alias_to_forbidden_edge(tmp_path: Path) -> None:
    write_module(tmp_path, "mailarium/model/__init__.py", "from mailarium import retrieval as search\n")

    rendered = [item.render(tmp_path) for item in checker.check(tmp_path)]

    assert rendered == [
        "mailarium/model/__init__.py:1 -> mailarium.model -> mailarium.retrieval (model must not import retrieval)"
    ]


def test_check_rejects_relative_parent_import_of_forbidden_package(tmp_path: Path) -> None:
    write_module(tmp_path, "mailarium/model/value.py", "from .. import retrieval\n")

    rendered = [item.render(tmp_path) for item in checker.check(tmp_path)]

    assert rendered == [
        "mailarium/model/value.py:1 -> mailarium.model.value -> mailarium.retrieval (model must not import retrieval)"
    ]


def test_check_rejects_star_import_from_forbidden_package(tmp_path: Path) -> None:
    write_module(tmp_path, "mailarium/model/value.py", "from mailarium.retrieval import *\n")

    rendered = [item.render(tmp_path) for item in checker.check(tmp_path)]

    assert rendered == [
        "mailarium/model/value.py:1 -> mailarium.model.value -> mailarium.retrieval (model must not import retrieval)"
    ]


def test_check_rejects_root_star_import_with_literal_forbidden_export(tmp_path: Path) -> None:
    write_module(tmp_path, "mailarium/__init__.py", '__all__ = ["retrieval"]\n')
    write_module(tmp_path, "mailarium/model/value.py", "from mailarium import *\n")

    rendered = [item.render(tmp_path) for item in checker.check(tmp_path)]

    assert rendered == ["mailarium/model/value.py:1 -> mailarium.model.value -> mailarium (root star imports are prohibited)"]


def test_check_rejects_root_star_import_with_literal_allowed_export(tmp_path: Path) -> None:
    write_module(tmp_path, "mailarium/__init__.py", '__all__ = ["retrieval"]\n')
    write_module(tmp_path, "mailarium/interfaces/value.py", "from mailarium import *\n")

    rendered = [item.render(tmp_path) for item in checker.check(tmp_path)]

    assert rendered == [
        "mailarium/interfaces/value.py:1 -> mailarium.interfaces.value -> mailarium (root star imports are prohibited)"
    ]


@pytest.mark.parametrize("mutation", ['__all__.append("retrieval")', '__all__.extend(["retrieval"])'])
def test_check_rejects_root_star_import_after_root_all_mutation(tmp_path: Path, mutation: str) -> None:
    write_module(tmp_path, "mailarium/__init__.py", f"__all__ = []\n{mutation}\n")
    write_module(tmp_path, "mailarium/model/value.py", "from mailarium import *\n")

    rendered = [item.render(tmp_path) for item in checker.check(tmp_path)]

    assert rendered == ["mailarium/model/value.py:1 -> mailarium.model.value -> mailarium (root star imports are prohibited)"]


def test_check_rejects_compatibility_package_imported_through_root_alias(tmp_path: Path) -> None:
    write_module(tmp_path, "mailarium/model/__init__.py", "from mailarium import compatibility as legacy\n")
    write_module(tmp_path, "mailarium/compatibility/__init__.py", "")

    rendered = [item.render(tmp_path) for item in checker.check(tmp_path)]

    assert rendered == [
        "mailarium/compatibility/__init__.py:1 -> mailarium.compatibility -> "
        "mailarium.compatibility (unknown architectural package: compatibility)",
        "mailarium/model/__init__.py:1 -> mailarium.model -> mailarium.compatibility (unknown root or package: compatibility)",
    ]


def test_check_rejects_unknown_root_import_without_flagging_root_symbol_import(tmp_path: Path) -> None:
    write_module(tmp_path, "mailarium/__init__.py", '__version__ = "test"\n')
    write_module(tmp_path, "mailarium/model/value.py", "from mailarium import __version__, vanished\n")

    rendered = [item.render(tmp_path) for item in checker.check(tmp_path)]

    assert rendered == [
        "mailarium/model/value.py:1 -> mailarium.model.value -> mailarium.vanished (unknown root or package: vanished)"
    ]


def test_root_composition_module_policy_reports_exact_edge_and_nonzero_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_module(tmp_path, "mailarium/cli.py", "from mailarium import archive\n")

    assert checker.main(["--root", str(tmp_path)]) == 1

    assert capsys.readouterr().out.splitlines() == [
        "Architectural dependency violations:",
        "mailarium/cli.py:1 -> mailarium.cli -> mailarium.archive (cli must not import archive)",
    ]
