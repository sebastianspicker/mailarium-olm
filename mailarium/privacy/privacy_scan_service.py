"""Orchestrate publication privacy scanning without rendering sensitive text."""

from __future__ import annotations

from pathlib import Path

from mailarium.privacy.privacy_scan_git import history_blobs, history_paths, run_git_bytes, tracked_paths, untracked_paths
from mailarium.privacy.privacy_scan_rules import (
    TRACKED_FORBIDDEN_PATH_PATTERNS,
    UNTRACKED_FORBIDDEN_PATH_PATTERNS,
    Finding,
    forbidden_path_findings,
    is_text_scan_path_candidate,
    text_findings,
)


def _scan_text(root: Path, paths: list[str]) -> list[Finding]:
    """Scan eligible files that exist in the prospective worktree publication."""
    findings: list[Finding] = []
    for path in paths:
        if not is_text_scan_path_candidate(path):
            continue
        try:
            text = (root / path).read_text(encoding="utf-8", errors="ignore")
        except FileNotFoundError:
            continue
        except OSError:
            findings.append(Finding("unreadable-candidate-file", path))
            continue
        findings.extend(text_findings(path, text))
    return findings


def _scan_history_text(root: Path) -> list[Finding]:
    """Scan each historical blob once and map its risks to every path."""
    findings: list[Finding] = []
    scanned_blob_hashes: set[str] = set()
    blob_matches: dict[str, list[str]] = {}
    for blob_hash, path in history_blobs(root):
        if not is_text_scan_path_candidate(path):
            continue
        if blob_hash not in scanned_blob_hashes:
            scanned_blob_hashes.add(blob_hash)
            text = run_git_bytes(root, ["cat-file", "-p", blob_hash], check=False).decode("utf-8", errors="ignore")
            blob_matches[blob_hash] = [finding.category for finding in text_findings(path, text)]
        findings.extend(Finding(f"history-{category}", path) for category in blob_matches.get(blob_hash, []))
    return findings


def scan(root: Path, *, include_untracked: bool = True, include_history: bool = False) -> list[Finding]:
    """Return stable, deduplicated publication-risk findings for ``root``."""
    findings: list[Finding] = []
    tracked = tracked_paths(root)
    findings.extend(forbidden_path_findings(tracked, TRACKED_FORBIDDEN_PATH_PATTERNS, "tracked-forbidden-path"))
    findings.extend(_scan_text(root, tracked))

    if include_untracked:
        untracked = untracked_paths(root)
        findings.extend(forbidden_path_findings(untracked, UNTRACKED_FORBIDDEN_PATH_PATTERNS, "untracked-private-artifact"))
        findings.extend(Finding(f"untracked-{finding.category}", finding.path) for finding in _scan_text(root, untracked))

    if include_history:
        findings.extend(forbidden_path_findings(history_paths(root), TRACKED_FORBIDDEN_PATH_PATTERNS, "history-risk-path"))
        findings.extend(_scan_history_text(root))

    return sorted(set(findings), key=lambda item: (item.category, item.path))
