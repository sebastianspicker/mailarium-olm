"""Ephemeral scan session for progressive multi-pass search.

Tracks seen UIDs and flagged candidates across multiple MCP tool calls,
enabling automatic cross-call deduplication and progressive refinement.
Sessions are in-memory and auto-expire after a configurable TTL.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_DEFAULT_SESSION_TTL = 3600  # 1 hour


@dataclass
class CandidateInfo:
    """A flagged email candidate within a scan session."""

    label: str
    phase: int
    score: float
    added_at: float = field(default_factory=time.time)


@dataclass
class ScanSession:
    """Server-side state for a progressive search session."""

    scan_id: str
    seen_uids: set[str] = field(default_factory=set)
    candidates: dict[str, CandidateInfo] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    # NOTE: threading.Lock is not picklable — ScanSession instances are
    # in-memory only and cannot be serialized (e.g. for multiprocessing or
    # persistent storage).
    lock: threading.Lock = field(default_factory=threading.Lock)

    def touch(self) -> None:
        """Update last-accessed timestamp to prevent TTL expiry."""
        self.last_accessed = time.time()

    def is_expired(self, ttl: float) -> bool:
        """Return True if the session has been idle longer than ttl seconds."""
        return (time.time() - self.last_accessed) > ttl


_sessions: dict[str, ScanSession] = {}
_lock = threading.Lock()


def _get_ttl() -> float:
    raw = os.environ.get("SCAN_SESSION_TTL")
    if raw is None:
        return float(_DEFAULT_SESSION_TTL)
    try:
        val = float(raw)
        if val <= 0 or val != val:  # reject <= 0 and NaN
            return float(_DEFAULT_SESSION_TTL)
        return val
    except (ValueError, TypeError):
        return float(_DEFAULT_SESSION_TTL)


def _cleanup_expired() -> None:
    """Remove expired sessions. Must be called under _lock."""
    ttl = _get_ttl()
    expired = [sid for sid, s in _sessions.items() if s.is_expired(ttl)]
    for sid in expired:
        del _sessions[sid]


def get_session(scan_id: str, *, auto_create: bool = True) -> ScanSession | None:
    """Get or auto-create a session. Cleans expired sessions on access.

    Memory safety: ``_cleanup_expired()`` runs on every call, evicting
    sessions whose ``last_accessed`` exceeds the TTL (default 1 hour).
    This prevents unbounded growth of the module-level ``_sessions`` dict.
    """
    with _lock:
        _cleanup_expired()
        session = _sessions.get(scan_id)
        if session is None and auto_create:
            session = ScanSession(scan_id=scan_id)
            _sessions[scan_id] = session
        if session is not None:
            session.touch()
        return session


def _extract_uid(result: object) -> str | None:
    """Extract UID from a SearchResult object or a dict."""
    if hasattr(result, "metadata"):
        return result.metadata.get("uid")
    if isinstance(result, dict):
        return result.get("uid")
    return None


def filter_seen(scan_id: str, results: list) -> tuple[list, dict]:
    """Filter results, removing already-seen UIDs.

    Returns ``(new_results, scan_metadata)``.  Adds all new UIDs to the
    session's ``seen_uids`` set.  Thread-safe via per-session lock.
    """
    session = get_session(scan_id)
    if session is None:  # pragma: no cover — auto_create=True guarantees this
        return [], {"scan_id": scan_id, "error": "session not found"}
    with session.lock:
        new_results: list = []
        excluded_count = 0
        for r in results:
            uid = _extract_uid(r)
            if uid and uid in session.seen_uids:
                excluded_count += 1
            else:
                new_results.append(r)
                if uid:
                    session.seen_uids.add(uid)

        scan_meta = {
            "scan_id": scan_id,
            "new_count": len(new_results),
            "excluded_count": excluded_count,
            "seen_total": len(session.seen_uids),
            "candidates_count": len(session.candidates),
        }
    return new_results, scan_meta


def flag_candidates(
    scan_id: str,
    uids: list[str],
    label: str,
    phase: int = 1,
    score: float = 0.0,
) -> tuple[int, int]:
    """Flag UIDs as candidates. Returns (newly_flagged, total_candidates).

    Thread-safe via per-session lock.
    """
    session = get_session(scan_id)
    if session is None:  # pragma: no cover — auto_create=True guarantees this
        return 0, 0
    with session.lock:
        added = 0
        for uid in uids:
            if uid not in session.candidates:
                added += 1
                session.candidates[uid] = CandidateInfo(
                    label=label,
                    phase=phase,
                    score=score,
                )
            else:
                logger.debug(
                    "flag_candidates: UID %s already flagged in scan %s, skipping",
                    uid,
                    scan_id,
                )
            session.seen_uids.add(uid)
        total = len(session.candidates)
    return added, total


def get_candidates(
    scan_id: str,
    *,
    label: str | None = None,
    phase: int | None = None,
) -> list[dict]:
    """Return candidates, optionally filtered by label and/or phase.

    Thread-safe via per-session lock (must hold lock while iterating
    ``session.candidates`` since ``flag_candidates`` mutates it concurrently).
    """
    session = get_session(scan_id, auto_create=False)
    if not session:
        return []
    with session.lock:
        result: list[dict] = []
        for uid, info in session.candidates.items():
            if label and info.label != label:
                continue
            if phase is not None and info.phase != phase:
                continue
            result.append(
                {
                    "uid": uid,
                    "label": info.label,
                    "phase": info.phase,
                    "score": info.score,
                }
            )
    return result


def session_status(scan_id: str) -> dict | None:
    """Return session stats or None if session doesn't exist.

    Thread-safe via per-session lock (must hold lock while iterating
    ``session.candidates`` and reading ``session.seen_uids``).
    """
    session = get_session(scan_id, auto_create=False)
    if not session:
        return None
    with session.lock:
        label_counts: dict[str, int] = {}
        phase_counts: dict[int, int] = {}
        for info in session.candidates.values():
            label_counts[info.label] = label_counts.get(info.label, 0) + 1
            phase_counts[info.phase] = phase_counts.get(info.phase, 0) + 1
        return {
            "scan_id": scan_id,
            "seen_count": len(session.seen_uids),
            "candidate_count": len(session.candidates),
            "candidates_by_label": label_counts,
            "candidates_by_phase": phase_counts,
            "created_at": session.created_at,
            "last_accessed": session.last_accessed,
            "age_seconds": round(time.time() - session.created_at),
        }


def reset_session(scan_id: str) -> bool:
    """Remove a session. Returns True if it existed."""
    with _lock:
        return _sessions.pop(scan_id, None) is not None


def reset_all_sessions() -> int:
    """Remove all sessions. Returns count removed."""
    with _lock:
        count = len(_sessions)
        _sessions.clear()
        return count
