"""Git-backed path and blob access for the publication privacy scan."""

from __future__ import annotations

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


def tracked_paths(root: Path) -> list[str]:
    """Enumerate paths represented in Git's current index."""
    return run_git(root, ["ls-files"])


def untracked_paths(root: Path) -> list[str]:
    """Enumerate unignored worktree paths absent from Git's index."""
    return run_git(root, ["ls-files", "--others", "--exclude-standard"])


def history_paths(root: Path) -> list[str]:
    """Enumerate every non-empty path recorded across all Git refs."""
    return sorted(set(run_git(root, ["log", "--all", "--name-only", "--pretty=format:"])))


def history_blobs(root: Path) -> list[tuple[str, str]]:
    """Map unique historical blob hashes to each path that referenced them."""
    blob_paths: dict[tuple[str, str], None] = {}
    for commit in run_git(root, ["rev-list", "--all"]):
        for record in run_git_bytes(root, ["ls-tree", "-rz", commit]).split(b"\0"):
            line = record.decode("utf-8", errors="ignore")
            if not line:
                continue
            try:
                meta, path = line.split("\t", 1)
                _mode, kind, blob_hash = meta.split(" ", 2)
            except ValueError:
                continue
            if kind == "blob":
                blob_paths[(blob_hash, path)] = None
    return sorted(blob_paths)
