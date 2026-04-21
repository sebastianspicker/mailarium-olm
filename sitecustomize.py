"""Process-wide startup compatibility shims for local repo runs."""

from src.transformers_compat import ensure_flagembedding_transformers_compat

ensure_flagembedding_transformers_compat()
