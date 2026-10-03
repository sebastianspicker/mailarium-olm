"""Git-backed path and blob access for the publication privacy scan."""

from __future__ import annotations

import os
import shutil
import subprocess  # nosec B404
from pathlib import Path

_GIT_PATH = shutil.which("git") or "git"


def run_git(root: Path, args: list[str], *, check: bool = True) -> list[str]:
    """Run a text Git query at ``root`` and discard blank output lines."""
    completed = subprocess.run(  # nosemgrep
        [_GIT_PATH, *args], cwd=root, check=check, capture_output=True, text=True
    )
    return [line for line in completed.stdout.splitlines() if line]


def run_git_bytes(root: Path, args: list[str], *, check: bool = True) -> bytes:
    """Run a binary-safe Git query at ``root``."""
    completed = subprocess.run(  # nosemgrep
        [_GIT_PATH, *args], cwd=root, check=check, capture_output=True
    )
    return completed.stdout


def _nul_paths(root: Path, args: list[str]) -> list[str]:
    """Decode NUL-delimited Git paths without Git display quoting or data loss."""
    return [os.fsdecode(raw) for raw in run_git_bytes(root, args).split(b"\0") if raw]


def tracked_paths(root: Path) -> list[str]:
    """Enumerate paths represented in Git's current index."""
    return _nul_paths(root, ["ls-files", "-z"])


def untracked_paths(root: Path) -> list[str]:
    """Enumerate unignored worktree paths absent from Git's index."""
    return _nul_paths(root, ["ls-files", "--others", "--exclude-standard", "-z"])


def history_paths(root: Path) -> list[str]:
    """Enumerate every non-empty path recorded across all Git refs."""
    return sorted(set(_nul_paths(root, ["log", "--all", "--name-only", "--pretty=format:", "-z"])))


def history_blobs(root: Path) -> list[tuple[str, str]]:
    """Map unique historical blob hashes to each path that referenced them."""
    blob_paths: dict[tuple[str, str], None] = {}
    for commit in run_git(root, ["rev-list", "--all"]):
        for record in run_git_bytes(root, ["ls-tree", "-rz", commit]).split(b"\0"):
            if not record:
                continue
            try:
                meta, raw_path = record.split(b"\t", 1)
                _mode, kind, blob_hash = meta.decode("ascii").split(" ", 2)
            except ValueError:
                continue
            if kind == "blob":
                blob_paths[(blob_hash, os.fsdecode(raw_path))] = None
    return sorted(blob_paths)
