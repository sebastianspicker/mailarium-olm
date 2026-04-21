"""Compatibility helpers for third-party transformers integrations."""

from __future__ import annotations

from typing import Any, cast


def ensure_flagembedding_transformers_compat() -> None:
    """Restore APIs removed in Transformers 5 that FlagEmbedding still imports.

    FlagEmbedding 1.3.5 imports ``is_torch_fx_available`` from
    ``transformers.utils.import_utils`` in its MiniCPM reranker modules.
    That symbol is absent in Transformers 5.x, which raises ImportError at
    module import time long before our own code can fall back gracefully.

    The legacy helper only gates an optional FX wrapper in FlagEmbedding's
    vendored model code, so returning ``False`` preserves the safe path.
    """
    try:
        from transformers.utils import import_utils
    except ImportError:
        return

    if hasattr(import_utils, "is_torch_fx_available"):
        return

    def is_torch_fx_available() -> bool:
        return False

    import_utils_any = cast(Any, import_utils)
    import_utils_any.is_torch_fx_available = is_torch_fx_available
