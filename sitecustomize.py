"""Process-wide startup compatibility shims for local repo runs.

ponytail: Only exists because transformers 5.0.0rc3 removed an internal
import path that FlagEmbedding depends on. This module monkeypatches
transformers.utils.import_utils at interpreter start to restore it.

Affects every Python process using this repo's venv (tests, tooling, CLI, etc.).
The monkeypatch is guarded (checks hasattr before patching) so it's a no-op
when the helper already exists.

DELETE THIS FILE when:
  - transformers ships 5.0 GA with a stable internal API, AND
  - FlagEmbedding drops the dependency on the removed FX helper.
Tracked by: pyproject.toml's transformers pin and the compatibility regression
tests in tests/test_transformers_compat.py.
"""

from src.transformers_compat import ensure_flagembedding_transformers_compat

ensure_flagembedding_transformers_compat()
