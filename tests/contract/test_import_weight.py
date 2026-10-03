"""Entry points and package roots must stay importable without heavy optional stacks.

CLI help, MCP startup, parser-only ingestion, and archive access must not load
model, NLP, dataframe, accelerator, or UI frameworks until a feature needs them.
"""

from __future__ import annotations

import subprocess  # nosec B404
import sys

import pytest

HEAVY_MODULES = (
    "torch",
    "sentence_transformers",
    "transformers",
    "spacy",
    "sklearn",
    "pandas",
    "networkx",
    "usearch",
    "streamlit",
    "datasets",
)

LIGHT_ENTRY_MODULES = (
    "mailarium.cli",
    "mailarium.ingest",
    "mailarium.mcp_server",
    "mailarium.archive",
    "mailarium.retrieval",
    "mailarium.ingestion",
    "mailarium.ingestion.olm",
)


@pytest.mark.parametrize("module", LIGHT_ENTRY_MODULES)
def test_entry_module_import_does_not_load_heavy_dependencies(module: str) -> None:
    probe = (
        "import importlib, json, sys\n"
        f"importlib.import_module({module!r})\n"
        f"print(json.dumps([name for name in {HEAVY_MODULES!r} if name in sys.modules]))\n"
    )
    completed = subprocess.run(  # nosec B603
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True, timeout=120
    )
    assert completed.stdout.strip().splitlines()[-1] == "[]"
