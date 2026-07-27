"""Regression coverage for the supported Python and dependency policy."""

from __future__ import annotations

import tomllib
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_project_metadata_declares_the_python_314_only_dependency_policy() -> None:
    with (REPOSITORY_ROOT / "pyproject.toml").open("rb") as metadata_file:
        project = tomllib.load(metadata_file)["project"]

    assert project["version"] == "0.5.0a1"
    assert project["name"] == "mailarium"
    assert project["requires-python"] == ">=3.14.6,<3.15"
    assert set(project["dependencies"]) >= {
        "usearch==2.26.0",
        "torch==2.13.0",
        "sentence-transformers==5.6.0",
        "transformers==5.13.0",
    }

    assert project["optional-dependencies"] == {
        "nlp": ["spacy==3.8.13"],
        "image": ["torchvision==0.28.0"],
        "training": ["datasets==5.0.0", "accelerate==1.14.0"],
        "ews": ["defusedxml>=0.7.1,<1"],
        "ews-ntlm": ["defusedxml>=0.7.1,<1", "requests-ntlm>=1.3.0,<2"],
        "dev": project["optional-dependencies"]["dev"],
    }

    scripts = project["scripts"]
    assert scripts == {
        "mailarium-ingest": "mailarium.ingest:main",
        "mailarium": "mailarium.cli:main",
    }

    tool_config = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]
    assert tool_config["ruff"]["target-version"] == "py314"
    assert tool_config["mypy"]["python_version"] == "3.14"
    assert tool_config["pytest"]["ini_options"]["testpaths"] == ["tests"]


def test_ci_uses_the_single_supported_python_patch_release() -> None:
    ci_workflow = (REPOSITORY_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert 'python-version: "3.14.6"' in ci_workflow
    assert "matrix:" not in ci_workflow
    assert "matrix.python-version" not in ci_workflow
    assert ci_workflow.count("--extra ews-ntlm") >= 4
    assert ci_workflow.count("--no-hashes") == 2
    assert ci_workflow.count("--output-file dist/requirements.locked.txt") == 2


def test_requirements_file_matches_the_core_retrieval_dependency_policy() -> None:
    requirements = (REPOSITORY_ROOT / "requirements.txt").read_text(encoding="utf-8").lower()

    for dependency in (
        "usearch==2.26.0",
        "torch==2.13.0",
        "sentence-transformers==5.6.0",
        "transformers==5.13.0",
    ):
        assert dependency in requirements
