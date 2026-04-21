"""Shared repository path and validation helpers."""

from __future__ import annotations

import os
import subprocess
from functools import lru_cache
from pathlib import Path

_DEFAULT_OUTPUT_ROOTS = ("private",)
_DEFAULT_LOCAL_READ_ROOTS = (
    "private",
    "data",
    "tests/private",
    "tests/fixtures",
)
_DEFAULT_RUNTIME_ROOTS = (
    "private",
    "data",
    "tests/private",
    "tests/fixtures",
)


def _split_env_path_list(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(os.pathsep) if part.strip()]


def repo_root() -> Path:
    """Return the stable repository root independent of process cwd."""
    return Path(__file__).resolve().parents[1]


def _normalized_roots(default_roots: tuple[str, ...], *, env_var: str) -> tuple[Path, ...]:
    root = repo_root()
    configured = _split_env_path_list(os.getenv(env_var, ""))
    roots: list[Path] = [root / rel for rel in default_roots]
    roots.extend(Path(item).expanduser() for item in configured)
    normalized: list[Path] = []
    seen: set[Path] = set()
    for candidate in roots:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        normalized.append(resolved)
        seen.add(resolved)
    return tuple(normalized)


def _validate_contained_path(value: str, *, field_name: str, roots: tuple[Path, ...], label: str) -> Path:
    normalized = normalize_local_path(value, field_name=field_name)
    if any(normalized.is_relative_to(root) for root in roots):
        return normalized
    allowed = ", ".join(str(root) for root in roots)
    raise ValueError(f"{field_name} must resolve inside allowed {label}: {allowed}")


def normalize_local_path(value: str, *, field_name: str = "path") -> Path:
    """Return an absolute normalized local path after baseline safety checks."""
    if "\x00" in value:
        raise ValueError(f"{field_name} must not contain null bytes")
    if ".." in Path(value).parts:
        raise ValueError(f"{field_name} must not traverse parent directories with '..'")
    return Path(value).expanduser().resolve()


@lru_cache(maxsize=1)
def _tracked_repo_paths() -> frozenset[str]:
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repo_root(),
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        return frozenset()
    return frozenset(path for path in completed.stdout.decode("utf-8", errors="ignore").split("\0") if path)


def _is_tracked_repo_path(path: Path) -> bool:
    root = repo_root()
    try:
        relative = path.resolve().relative_to(root).as_posix()
    except ValueError:
        return False
    return relative in _tracked_repo_paths()


def allowed_output_roots() -> tuple[Path, ...]:
    """Return normalized allowlisted roots for write/output paths."""
    return _normalized_roots(_DEFAULT_OUTPUT_ROOTS, env_var="EMAIL_RAG_ALLOWED_OUTPUT_ROOTS")


def allowed_local_read_roots() -> tuple[Path, ...]:
    """Return normalized allowlisted roots for local file and directory reads."""
    return _normalized_roots(_DEFAULT_LOCAL_READ_ROOTS, env_var="EMAIL_RAG_ALLOWED_LOCAL_READ_ROOTS")


def allowed_runtime_roots() -> tuple[Path, ...]:
    """Return normalized allowlisted roots for destructive runtime operations."""
    return _normalized_roots(_DEFAULT_RUNTIME_ROOTS, env_var="EMAIL_RAG_ALLOWED_RUNTIME_ROOTS")


def validate_output_path(value: str, *, field_name: str = "Output path") -> Path:
    """Validate output path containment under configured write roots."""
    path = Path(value)
    if path.is_absolute():
        normalized = normalize_local_path(value, field_name=field_name)
    else:
        normalized = normalize_local_path(str(repo_root() / path), field_name=field_name)
    roots = allowed_output_roots()
    if any(normalized.is_relative_to(root) for root in roots):
        if _is_tracked_repo_path(normalized):
            raise ValueError(f"{field_name} must not target a tracked repository file: {normalized}")
        return normalized
    allowed = ", ".join(str(root) for root in roots)
    raise ValueError(f"{field_name} must resolve inside allowed output roots: {allowed}")


def validate_new_output_path(value: str, *, field_name: str = "Output path") -> Path:
    """Validate an output path and reject overwriting any existing path."""
    normalized = validate_output_path(value, field_name=field_name)
    if normalized.exists():
        raise ValueError(f"{field_name} already exists and will not be overwritten: {normalized}")
    return normalized


def validate_local_read_path(value: str, *, field_name: str = "path") -> Path:
    """Validate local read paths against allowlisted roots."""
    return _validate_contained_path(
        value,
        field_name=field_name,
        roots=allowed_local_read_roots(),
        label="local read roots",
    )


def validate_runtime_path(value: str, *, field_name: str = "path") -> Path:
    """Validate destructive runtime paths against allowlisted roots."""
    return _validate_contained_path(
        value,
        field_name=field_name,
        roots=allowed_runtime_roots(),
        label="runtime roots",
    )
