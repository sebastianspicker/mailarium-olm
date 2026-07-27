"""Shared repository path and validation helpers."""

from __future__ import annotations

import os
import shutil
import subprocess  # nosec B404
import sys
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
_RUNTIME_HOME_ENV = "MAILARIUM_RUNTIME_HOME"
_LEGACY_ENV_REPLACEMENTS = {
    "EMAIL_RAG_RUNTIME_HOME": _RUNTIME_HOME_ENV,
    "EMAIL_RAG_ALLOWED_OUTPUT_ROOTS": "MAILARIUM_ALLOWED_OUTPUT_ROOTS",
    "EMAIL_RAG_ALLOWED_LOCAL_READ_ROOTS": "MAILARIUM_ALLOWED_LOCAL_READ_ROOTS",
    "EMAIL_RAG_ALLOWED_RUNTIME_ROOTS": "MAILARIUM_ALLOWED_RUNTIME_ROOTS",
}


def _reject_legacy_environment() -> None:
    """Reject removed product-prefixed variables instead of silently ignoring them."""
    for legacy_name, replacement in _LEGACY_ENV_REPLACEMENTS.items():
        if legacy_name in os.environ:
            raise ValueError(f"{legacy_name} was removed in 0.5; use {replacement}")


def _split_env_path_list(raw: str) -> list[str]:
    """Split an environment path list string by the OS path separator."""
    return [part.strip() for part in raw.split(os.pathsep) if part.strip()]


def repo_root() -> Path:
    """Locate the source checkout root used by repository-relative defaults."""
    return Path(__file__).resolve().parents[1]


def _is_repository_checkout() -> bool:
    root = repo_root()
    return (root / "pyproject.toml").is_file() and (root / ".git").exists()


def _platform_runtime_home() -> Path:
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "mailarium"
    if os.name == "nt":
        local_app_data = os.getenv("LOCALAPPDATA")
        base = Path(local_app_data).expanduser() if local_app_data else home / "AppData" / "Local"
        return base / "mailarium"
    xdg_data_home = os.getenv("XDG_DATA_HOME")
    base = Path(xdg_data_home).expanduser() if xdg_data_home else home / ".local" / "share"
    return base / "mailarium"


def runtime_home() -> Path:
    """Choose an absolute runtime data directory, honoring the explicit environment override."""
    _reject_legacy_environment()
    configured = os.getenv(_RUNTIME_HOME_ENV)
    if configured:
        candidate = Path(configured).expanduser()
        if not candidate.is_absolute():
            raise ValueError(f"{_RUNTIME_HOME_ENV} must be an absolute path")
        return normalize_local_path(str(candidate), field_name=_RUNTIME_HOME_ENV)
    if _is_repository_checkout():
        return repo_root().resolve()
    return _platform_runtime_home().resolve()


def _normalized_roots(default_roots: tuple[str, ...], *, env_var: str) -> tuple[Path, ...]:
    """Get normalized path roots from defaults and environment variable."""
    _reject_legacy_environment()
    root = repo_root()
    configured = _split_env_path_list(os.getenv(env_var, ""))
    roots: list[Path] = [root / rel for rel in default_roots]
    roots.extend(Path(item).expanduser() for item in configured)
    return _deduplicated_resolved_roots(roots)


def _deduplicated_resolved_roots(roots: list[Path]) -> tuple[Path, ...]:
    """Resolve a root list while preserving its first-seen order."""
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
    """Validate that a path is contained within one of the allowed roots."""
    normalized = normalize_local_path(value, field_name=field_name)
    if any(normalized.is_relative_to(root) for root in roots):
        return normalized
    allowed = ", ".join(str(root) for root in roots)
    raise ValueError(f"{field_name} must resolve inside allowed {label}: {allowed}")


def normalize_local_path(value: str, *, field_name: str = "path") -> Path:
    """Resolve a local path after rejecting null bytes and parent-directory traversal."""
    if "\x00" in value:
        raise ValueError(f"{field_name} must not contain null bytes")
    if ".." in Path(value).parts:
        raise ValueError(f"{field_name} must not traverse parent directories with '..'")
    return Path(value).expanduser().resolve()


@lru_cache(maxsize=1)
def _tracked_repo_paths() -> frozenset[str]:
    """Get all paths tracked by git in the repository."""
    git_path = shutil.which("git") or "git"
    completed = subprocess.run(  # nosemgrep
        [git_path, "ls-files", "-z"],
        cwd=repo_root(),
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        return frozenset()
    return frozenset(path for path in completed.stdout.decode("utf-8", errors="ignore").split("\0") if path)


def _is_tracked_repo_path(path: Path) -> bool:
    """Check if a path is tracked by git in the repository."""
    root = repo_root()
    try:
        relative = path.resolve().relative_to(root).as_posix()
    except ValueError:
        return False
    return relative in _tracked_repo_paths()


def allowed_output_roots() -> tuple[Path, ...]:
    """Return normalized output roots configured for safe artifact writes."""
    return _normalized_roots(_DEFAULT_OUTPUT_ROOTS, env_var="MAILARIUM_ALLOWED_OUTPUT_ROOTS")


def allowed_local_read_roots() -> tuple[Path, ...]:
    """Return normalized local roots from which tools may read user-provided files."""
    return _normalized_roots(_DEFAULT_LOCAL_READ_ROOTS, env_var="MAILARIUM_ALLOWED_LOCAL_READ_ROOTS")


def allowed_runtime_roots() -> tuple[Path, ...]:
    """Return runtime roots appropriate to an installed app or an editable repository checkout."""
    _reject_legacy_environment()
    if os.getenv(_RUNTIME_HOME_ENV) or not _is_repository_checkout():
        configured = _split_env_path_list(os.getenv("MAILARIUM_ALLOWED_RUNTIME_ROOTS", ""))
        roots = [runtime_home(), *(Path(item).expanduser() for item in configured)]
        return _deduplicated_resolved_roots(roots)
    return _normalized_roots(_DEFAULT_RUNTIME_ROOTS, env_var="MAILARIUM_ALLOWED_RUNTIME_ROOTS")


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
    path = Path(value)
    if not path.is_absolute():
        value = str(runtime_home() / path)
    return _validate_contained_path(
        value,
        field_name=field_name,
        roots=allowed_runtime_roots(),
        label="runtime roots",
    )
