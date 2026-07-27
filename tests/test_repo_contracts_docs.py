"""Ensures public metadata and documentation describe only the current interfaces, storage, and MCP surface.

It prevents stale launch instructions, screenshots, and internal documentation paths from being advertised.
"""

from __future__ import annotations

import re
import struct
import tomllib

import pytest

from .helpers.repo_contracts import REPO_ROOT, _mcp_tool_count, _mcp_tools, _read


def _read_env_example() -> str:
    try:
        return _read(".env.example")
    except PermissionError:
        pytest.skip("managed workspace policy denies reading .env.example")


def test_env_example_uses_current_runtime_names() -> None:
    env_example = _read_env_example()

    assert "VECTOR_INDEX_PATH=private/runtime/current/vector-index" in env_example
    assert "SQLITE_PATH=private/runtime/current/email_metadata.db" in env_example
    assert "RUNTIME_PROFILE=quality" in env_example
    for variable in (
        "MAILARIUM_RUNTIME_HOME",
        "MAILARIUM_ALLOWED_OUTPUT_ROOTS",
        "MAILARIUM_ALLOWED_LOCAL_READ_ROOTS",
        "MAILARIUM_ALLOWED_RUNTIME_ROOTS",
    ):
        assert variable in env_example
    assert "EMAIL_RAG_" not in env_example
    assert "CHROMADB_PATH" not in env_example
    assert "LEGAL_DOMAIN_PACK_ENABLED" not in env_example


def test_project_metadata_and_docs_agree_on_python_and_version() -> None:
    project = tomllib.loads(_read("pyproject.toml"))["project"]
    readme = _read("README.md")
    releasing = _read("RELEASING.md")

    assert project["version"] == "0.5.0a1"
    assert project["name"] == "mailarium"
    assert project["requires-python"] == ">=3.14.6,<3.15"
    assert "Python 3.14.6" in readme
    assert "`0.5.0a1`" in readme
    assert "Package version: `0.5.0a1`" in releasing
    assert "Supported Python: `3.14.6`" in releasing


def test_mailarium_is_the_only_packaged_python_namespace() -> None:
    metadata = tomllib.loads(_read("pyproject.toml"))

    assert metadata["tool"]["setuptools"]["packages"]["find"]["include"] == ["mailarium*"]
    assert (REPO_ROOT / "mailarium").is_dir()
    assert not (REPO_ROOT / "src").exists()
    assert not (REPO_ROOT / "ews_inbox_assistant").exists()


def test_readme_documents_current_storage_and_interface_boundaries() -> None:
    readme = _read("README.md")

    assert "SQLite vectors + USearch" in readme
    assert "private/runtime/current/vector-index" in readme
    assert "private/runtime/current/email_metadata.db" in readme
    assert "CLI subcommands are the supported command interface" in readme
    assert "legal-domain-pack" not in readme
    assert "LEGAL_DOMAIN_PACK_ENABLED" not in readme
    assert not re.search(r"badge/tests-\d+", readme)


def test_readme_mcp_tool_count_matches_registered_surface() -> None:
    readme = _read("README.md")
    tool_count = _mcp_tool_count()

    assert f"Mailarium exposes {tool_count} MCP tools by default." in readme
    assert "img.shields.io" not in readme


def test_public_docs_index_only_routes_to_current_surfaces() -> None:
    docs_index = _read("docs/README.md")
    compatibility = _read("docs/API_COMPATIBILITY.md")
    cli_reference = _read("docs/CLI_REFERENCE.md")

    for path in (
        "ARCHITECTURE_AND_METHODS.md",
        "ANSWER_GROUNDING.md",
        "ATTACHMENT_SUPPORT.md",
        "README_USAGE_AND_OPERATIONS.md",
        "CLI_REFERENCE.md",
        "MCP_TOOLS.md",
        "PRIVACY_AND_REDACTION.md",
        "RUNTIME_TUNING.md",
        "API_COMPATIBILITY.md",
    ):
        assert path in docs_index
    assert "legal-domain-pack" not in docs_index
    assert "mailarium search" in cli_reference
    assert "Legacy Flat-Flag" not in cli_reference
    assert "Deliberate Breaks In 0.5" in compatibility
    assert "`0.5.x` alpha line" in docs_index
    assert "`src` and `ews_inbox_assistant` are no longer importable packages" in compatibility
    assert "- `mailbox`" in compatibility
    assert "There is no automatic migration or old-path fallback" in _read("docs/README_USAGE_AND_OPERATIONS.md")
    assert "Python 3.14.6" in compatibility


def test_release_status_preserves_the_exact_ews_verification_boundary() -> None:
    release_status = _read("RELEASE_STATUS.md")

    assert "Offline verified; live EWS writes unverified." in release_status


def test_answer_grounding_documents_the_runtime_payload_field() -> None:
    grounding = _read("docs/ANSWER_GROUNDING.md")
    runtime_payload = _read("mailarium/tools/search_answer_context_runtime_payload.py")

    assert "`final_answer`" in grounding
    assert "rendered_answer" not in grounding
    assert '"final_answer": _render_final_answer(' in runtime_payload


def test_attachment_support_documents_optional_install_and_release_smoke() -> None:
    attachment_support = _read("docs/ATTACHMENT_SUPPORT.md")
    releasing = _read("RELEASING.md")

    for dependency in ("PyPDF2", "python-docx", "openpyxl", "python-pptx"):
        assert dependency in attachment_support
        assert dependency in releasing
    for executable in ("tesseract", "pdftoppm"):
        assert f"{executable} --version" in attachment_support or f"{executable} -v" in attachment_support
        assert executable in releasing
    assert "tests/test_attachment_extractor_text_extraction.py" in releasing
    assert "tests/test_attachment_extractor_ocr_state.py" in releasing


def test_cli_and_streamlit_docs_only_advertise_current_launch_paths() -> None:
    cli_reference = _read("docs/CLI_REFERENCE.md")
    operations = _read("docs/README_USAGE_AND_OPERATIONS.md")

    assert "mailarium-ingest" in cli_reference
    assert "mailarium ingest " not in cli_reference
    assert "admin reembed" not in cli_reference
    assert "python -m streamlit run mailarium/web_app.py --server.address 127.0.0.1" in operations
    assert "python -m mailarium.cli" in cli_reference
    assert "python -m mailarium.ingest" in cli_reference


def test_mcp_reference_lists_every_registered_tool_and_current_server_command() -> None:
    mcp_reference = _read("docs/MCP_TOOLS.md")
    registered = set(_mcp_tools())

    assert "mailarium-mcp" not in mcp_reference
    assert "python -m mailarium.mcp_server" in mcp_reference
    assert len(registered) == 54
    assert all(f"`{tool_name}`" in mcp_reference for tool_name in registered)


def test_internal_agent_documentation_tree_is_absent() -> None:
    assert not (REPO_ROOT / "docs" / "agent").exists()


def test_documentation_images_track_current_streamlit_controls() -> None:
    app_source = _read("mailarium/web_app.py") + _read("mailarium/web_app_search.py") + _read("mailarium/web_app_rendering.py")
    explainer_svg = _read("docs/screenshots/retrieval-scope-ui.svg")
    readme = _read("README.md")
    screenshot_names = (
        "streamlit-empty-archive.png",
        "streamlit-search-ui.png",
        "streamlit-dashboard-ui.png",
    )

    for screenshot_name in screenshot_names:
        screenshot = (REPO_ROOT / "docs/screenshots" / screenshot_name).read_bytes()
        assert screenshot.startswith(b"\x89PNG\r\n\x1a\n")
        assert struct.unpack(">II", screenshot[16:24]) == (1440, 900)
        assert f"docs/screenshots/{screenshot_name}" in readme
    assert "isolated temporary runtime" in _read("docs/screenshots/README.md")
    assert not (REPO_ROOT / "docs/screenshots/streamlit-search-ui.svg").exists()
    for label in ("Search Mode", "Retrieval Scope"):
        assert label in app_source
        assert label in explainer_svg
    assert "not a literal Streamlit capture" in explainer_svg


def test_public_metadata_uses_canonical_github_urls() -> None:
    canonical = "https://github.com/sebastianspicker/outlook-email-rag"
    urls = tomllib.loads(_read("pyproject.toml"))["project"]["urls"]

    assert urls["Repository"] == canonical
    assert urls["Homepage"] == canonical
    assert urls["Issues"] == f"{canonical}/issues"
    assert urls["Documentation"] == f"{canonical}/tree/main/docs"
