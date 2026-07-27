"""Ensures public documentation links resolve to current repository paths without escaping the checkout."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

import pytest

REPO_ROOT = Path(__file__).parents[1]
PUBLIC_DOCS = (
    "README.md",
    "CHANGELOG.md",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "DESIGN.md",
    "PRODUCT.md",
    "RELEASE_STATUS.md",
    "RELEASING.md",
    "SECURITY.md",
    "SUPPORT.md",
    "docs/API_COMPATIBILITY.md",
    "docs/ANSWER_GROUNDING.md",
    "docs/ARCHITECTURE_AND_METHODS.md",
    "docs/ATTACHMENT_SUPPORT.md",
    "docs/CLI_REFERENCE.md",
    "docs/MCP_TOOLS.md",
    "docs/PRIVACY_AND_REDACTION.md",
    "docs/README.md",
    "docs/README_USAGE_AND_OPERATIONS.md",
    "docs/RUNTIME_TUNING.md",
    "docs/archive/README.md",
    "docs/archive/2026-07-24-superseded-search-mockups/README.md",
    "docs/screenshots/README.md",
    "tests/README.md",
    "tests/fixtures/qa_eval/PROVENANCE.md",
)
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


@pytest.mark.parametrize("relative_path", PUBLIC_DOCS)
def test_public_documentation_local_links_resolve(relative_path: str) -> None:
    source = REPO_ROOT / relative_path
    text = source.read_text(encoding="utf-8")
    missing: list[str] = []

    for raw_target in MARKDOWN_LINK.findall(text):
        target = raw_target.strip().strip("<>").split(maxsplit=1)[0]
        if not target or target.startswith(("#", "http://", "https://", "mailto:")):
            continue
        path_text = unquote(target.split("#", maxsplit=1)[0])
        resolved = (source.parent / path_text).resolve()
        try:
            resolved.relative_to(REPO_ROOT)
        except ValueError:
            missing.append(f"{target} (outside repository)")
            continue
        if not resolved.exists():
            missing.append(target)

    assert not missing, f"{relative_path} has unresolved local links: {missing}"
