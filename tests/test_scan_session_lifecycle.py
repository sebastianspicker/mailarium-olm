"""Lifecycle-phase scan session tests split from the RF11 catch-all."""

from __future__ import annotations

import time

import pytest

pytest_plugins = ["tests._scan_session_cases"]


class TestScanSessionCore:
    def test_auto_create_on_first_access(self):
        from src.scan_session import get_session

        session = get_session("test1")
        assert session is not None
        assert session.scan_id == "test1"
        assert len(session.seen_uids) == 0
        assert len(session.candidates) == 0

    def test_get_nonexistent_returns_none_without_auto_create(self):
        from src.scan_session import get_session

        session = get_session("nonexistent", auto_create=False)
        assert session is None

    def test_same_scan_id_returns_same_session(self):
        from src.scan_session import get_session

        session_one = get_session("test")
        session_one.seen_uids.add("uid1")
        session_two = get_session("test")
        assert "uid1" in session_two.seen_uids

    def test_different_scan_ids_are_independent(self):
        from src.scan_session import get_session

        session_one = get_session("a")
        session_one.seen_uids.add("uid1")
        session_two = get_session("b")
        assert "uid1" not in session_two.seen_uids


class TestFilterSeen:
    def make_result(self, uid, score=0.5):
        class FakeResult:
            def __init__(self, uid, score):
                self.metadata = {"uid": uid}
                self.score = score

        return FakeResult(uid, score)

    def test_first_call_returns_all(self):
        from src.scan_session import filter_seen

        results = [self.make_result("uid1"), self.make_result("uid2")]
        new, meta = filter_seen("test", results)
        assert len(new) == 2
        assert meta["new_count"] == 2
        assert meta["excluded_count"] == 0
        assert meta["seen_total"] == 2

    def test_second_call_excludes_seen(self):
        from src.scan_session import filter_seen

        results_one = [self.make_result("uid1"), self.make_result("uid2")]
        filter_seen("test", results_one)

        results_two = [self.make_result("uid2"), self.make_result("uid3")]
        new, meta = filter_seen("test", results_two)
        assert len(new) == 1
        assert new[0].metadata["uid"] == "uid3"
        assert meta["new_count"] == 1
        assert meta["excluded_count"] == 1
        assert meta["seen_total"] == 3

    def test_filter_seen_with_dicts(self):
        from src.scan_session import filter_seen

        results = [{"uid": "uid1", "text": "hello"}, {"uid": "uid2", "text": "world"}]
        new, _meta = filter_seen("test", results)
        assert len(new) == 2

        results_two = [{"uid": "uid1", "text": "hello again"}]
        new_two, meta_two = filter_seen("test", results_two)
        assert len(new_two) == 0
        assert meta_two["excluded_count"] == 1

    def test_filter_seen_handles_missing_uid(self):
        from src.scan_session import filter_seen

        results = [{"text": "no uid"}, self.make_result("uid1")]
        new, meta = filter_seen("test", results)
        assert len(new) == 2
        assert meta["new_count"] == 2

    def test_scan_metadata_fields(self):
        from src.scan_session import filter_seen

        results = [self.make_result("uid1")]
        _, meta = filter_seen("test_session", results)
        assert meta["scan_id"] == "test_session"
        assert "new_count" in meta
        assert "excluded_count" in meta
        assert "seen_total" in meta
        assert "candidates_count" in meta


class TestCandidates:
    def test_flag_candidates_basic(self):
        from src.scan_session import flag_candidates, get_session

        added, total = flag_candidates("test", ["uid1", "uid2"], label="bossing", phase=1, score=0.9)
        assert added == 2
        assert total == 2
        session = get_session("test")
        assert "uid1" in session.candidates
        assert session.candidates["uid1"].label == "bossing"
        assert session.candidates["uid1"].phase == 1
        assert session.candidates["uid1"].score == 0.9

    def test_flag_adds_to_seen(self):
        from src.scan_session import flag_candidates, get_session

        flag_candidates("test", ["uid1"], label="relevant")
        session = get_session("test")
        assert "uid1" in session.seen_uids

    def test_flag_skips_existing(self):
        from src.scan_session import flag_candidates, get_session

        flag_candidates("test", ["uid1"], label="maybe", phase=1)
        added, total = flag_candidates("test", ["uid1"], label="bossing", phase=2)
        assert added == 0
        assert total == 1
        session = get_session("test")
        assert session.candidates["uid1"].label == "maybe"
        assert session.candidates["uid1"].phase == 1

    def test_get_candidates_unfiltered(self):
        from src.scan_session import flag_candidates, get_candidates

        flag_candidates("test", ["uid1"], label="bossing", phase=1)
        flag_candidates("test", ["uid2"], label="harassment", phase=2)
        candidates = get_candidates("test")
        assert len(candidates) == 2

    def test_get_candidates_filter_by_label(self):
        from src.scan_session import flag_candidates, get_candidates

        flag_candidates("test", ["uid1"], label="bossing")
        flag_candidates("test", ["uid2"], label="harassment")
        candidates = get_candidates("test", label="bossing")
        assert len(candidates) == 1
        assert candidates[0]["uid"] == "uid1"

    def test_get_candidates_filter_by_phase(self):
        from src.scan_session import flag_candidates, get_candidates

        flag_candidates("test", ["uid1"], label="bossing", phase=1)
        flag_candidates("test", ["uid2"], label="bossing", phase=2)
        candidates = get_candidates("test", phase=2)
        assert len(candidates) == 1
        assert candidates[0]["uid"] == "uid2"

    def test_get_candidates_empty_session(self):
        from src.scan_session import get_candidates

        candidates = get_candidates("nonexistent")
        assert candidates == []


class TestSessionStatus:
    def test_status_fields(self):
        from src.scan_session import flag_candidates, get_session, session_status

        get_session("test").seen_uids.update(["uid1", "uid2", "uid3"])
        flag_candidates("test", ["uid1"], label="bossing", phase=1)
        flag_candidates("test", ["uid2"], label="harassment", phase=2)
        status = session_status("test")
        assert status["scan_id"] == "test"
        assert status["seen_count"] == 3
        assert status["candidate_count"] == 2
        assert status["candidates_by_label"] == {"bossing": 1, "harassment": 1}
        assert status["candidates_by_phase"] == {1: 1, 2: 1}
        assert "age_seconds" in status

    def test_status_nonexistent(self):
        from src.scan_session import session_status

        assert session_status("nonexistent") is None


class TestSessionReset:
    def test_reset_existing(self):
        from src.scan_session import get_session, reset_session

        get_session("test")
        assert reset_session("test") is True

    def test_reset_nonexistent(self):
        from src.scan_session import reset_session

        assert reset_session("nonexistent") is False

    def test_reset_all(self):
        from src.scan_session import get_session, reset_all_sessions

        get_session("a")
        get_session("b")
        count = reset_all_sessions()
        assert count == 2

    def test_session_expiry(self, monkeypatch):
        from src.scan_session import _sessions, get_session

        monkeypatch.setenv("SCAN_SESSION_TTL", "1")
        session = get_session("test")
        session.last_accessed = time.time() - 10
        result = get_session("test", auto_create=False)
        assert result is None
        assert "test" not in _sessions


class TestEmailScanInputModel:
    def test_defaults(self):
        from src.mcp_models import EmailScanInput

        model = EmailScanInput(action="status", scan_id="test")
        assert model.action == "status"
        assert model.scan_id == "test"
        assert model.uids is None
        assert model.label is None
        assert model.phase is None
        assert model.score is None

    def test_scan_id_required(self):
        from src.mcp_models import EmailScanInput

        with pytest.raises(ValueError):
            EmailScanInput(action="status")

    def test_scan_id_max_length(self):
        from src.mcp_models import EmailScanInput

        with pytest.raises(ValueError):
            EmailScanInput(action="status", scan_id="x" * 101)

    def test_uids_max_50(self):
        from src.mcp_models import EmailScanInput

        with pytest.raises(ValueError):
            EmailScanInput(
                action="flag",
                scan_id="test",
                uids=[f"uid{i}" for i in range(51)],
                label="relevant",
            )

    def test_phase_bounds(self):
        from src.mcp_models import EmailScanInput

        with pytest.raises(ValueError):
            EmailScanInput(action="flag", scan_id="test", phase=0)
        with pytest.raises(ValueError):
            EmailScanInput(action="flag", scan_id="test", phase=4)

    def test_score_bounds(self):
        from src.mcp_models import EmailScanInput

        with pytest.raises(ValueError):
            EmailScanInput(action="flag", scan_id="test", score=1.5)


class TestScanIdOnSearchModels:
    def test_triage_scan_id_optional(self):
        from src.mcp_models import EmailTriageInput

        model = EmailTriageInput(query="test")
        assert model.scan_id is None
        model_two = EmailTriageInput(query="test", scan_id="sess1")
        assert model_two.scan_id == "sess1"

    def test_structured_scan_id_optional(self):
        from src.mcp_models import EmailSearchStructuredInput

        model = EmailSearchStructuredInput(query="test")
        assert model.scan_id is None
        model_two = EmailSearchStructuredInput(query="test", scan_id="sess1")
        assert model_two.scan_id == "sess1"

    def test_find_similar_scan_id_optional(self):
        from src.mcp_models import FindSimilarInput

        model = FindSimilarInput(uid="uid1")
        assert model.scan_id is None
        model_two = FindSimilarInput(uid="uid1", scan_id="sess1")
        assert model_two.scan_id == "sess1"
