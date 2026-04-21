import sys
import types

from src.transformers_compat import ensure_flagembedding_transformers_compat


def test_ensure_flagembedding_transformers_compat_adds_missing_helper(monkeypatch):
    import_utils = types.ModuleType("transformers.utils.import_utils")
    utils = types.ModuleType("transformers.utils")
    transformers = types.ModuleType("transformers")

    utils.import_utils = import_utils
    transformers.utils = utils

    monkeypatch.setitem(sys.modules, "transformers", transformers)
    monkeypatch.setitem(sys.modules, "transformers.utils", utils)
    monkeypatch.setitem(sys.modules, "transformers.utils.import_utils", import_utils)

    ensure_flagembedding_transformers_compat()

    assert hasattr(import_utils, "is_torch_fx_available")
    assert import_utils.is_torch_fx_available() is False


def test_ensure_flagembedding_transformers_compat_keeps_existing_helper(monkeypatch):
    sentinel = object()

    import_utils = types.ModuleType("transformers.utils.import_utils")
    import_utils.is_torch_fx_available = lambda: sentinel
    utils = types.ModuleType("transformers.utils")
    transformers = types.ModuleType("transformers")

    utils.import_utils = import_utils
    transformers.utils = utils

    monkeypatch.setitem(sys.modules, "transformers", transformers)
    monkeypatch.setitem(sys.modules, "transformers.utils", utils)
    monkeypatch.setitem(sys.modules, "transformers.utils.import_utils", import_utils)

    ensure_flagembedding_transformers_compat()

    assert import_utils.is_torch_fx_available() is sentinel
