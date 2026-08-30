"""Contracts for deterministic native search loading."""

from __future__ import annotations

import os
from types import ModuleType

import pytest

from mailarium.archive import usearch_loader


def test_darwin_preloads_numkong_with_global_symbols(monkeypatch: pytest.MonkeyPatch) -> None:
    """NumKong loads globally before USearch while interpreter flags are restored."""
    original_flags = 2
    active_flags = original_flags
    imports: list[tuple[str, int]] = []
    usearch_module = ModuleType("usearch")

    def set_flags(value: int) -> None:
        nonlocal active_flags
        active_flags = value

    def import_module(name: str) -> ModuleType:
        imports.append((name, active_flags))
        return usearch_module if name == "usearch" else ModuleType(name)

    monkeypatch.setattr(usearch_loader.sys, "platform", "darwin")
    monkeypatch.setattr(usearch_loader.sys, "getdlopenflags", lambda: original_flags)
    monkeypatch.setattr(usearch_loader.sys, "setdlopenflags", set_flags)
    monkeypatch.setattr(usearch_loader.importlib, "import_module", import_module)

    assert usearch_loader.import_usearch() is usearch_module
    assert imports == [("numkong", original_flags | os.RTLD_GLOBAL), ("usearch", original_flags)]
    assert active_flags == original_flags


def test_darwin_restores_flags_when_numkong_import_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """A native preload failure propagates without leaking global loader flags."""
    original_flags = 2
    active_flags = original_flags

    def set_flags(value: int) -> None:
        nonlocal active_flags
        active_flags = value

    def import_module(name: str) -> ModuleType:
        raise ImportError(f"cannot import {name}")

    monkeypatch.setattr(usearch_loader.sys, "platform", "darwin")
    monkeypatch.setattr(usearch_loader.sys, "getdlopenflags", lambda: original_flags)
    monkeypatch.setattr(usearch_loader.sys, "setdlopenflags", set_flags)
    monkeypatch.setattr(usearch_loader.importlib, "import_module", import_module)

    with pytest.raises(ImportError, match="cannot import numkong"):
        usearch_loader.import_usearch()
    assert active_flags == original_flags


def test_non_darwin_import_does_not_change_loader_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    """Other platforms delegate directly to the normal USearch import."""
    usearch_module = ModuleType("usearch")
    imports: list[str] = []

    def import_module(name: str) -> ModuleType:
        imports.append(name)
        return usearch_module

    def unexpected_flag_access(*args: object) -> int:
        raise AssertionError(f"unexpected loader flag access: {args}")

    monkeypatch.setattr(usearch_loader.sys, "platform", "linux")
    monkeypatch.setattr(usearch_loader.sys, "getdlopenflags", unexpected_flag_access)
    monkeypatch.setattr(usearch_loader.sys, "setdlopenflags", unexpected_flag_access)
    monkeypatch.setattr(usearch_loader.importlib, "import_module", import_module)

    assert usearch_loader.import_usearch() is usearch_module
    assert imports == ["usearch"]
