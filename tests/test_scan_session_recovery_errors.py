"""Recovery, reset, and concurrency scan-session tests split from the RF11 catch-all."""

from __future__ import annotations

import threading

import pytest

pytest_plugins = ["tests._scan_session_cases"]


@pytest.mark.asyncio
async def test_email_scan_reset():
    from src import scan_session

    scan_session.get_session("test")
    assert scan_session.reset_session("test") is True
    assert scan_session.session_status("test") is None


class TestFilterSeenThreadSafety:
    """Verify concurrent scan-session access remains safe."""

    def test_concurrent_filter_seen_no_duplicates(self):
        from src.scan_session import filter_seen, get_session

        scan_id = "thread_test"
        get_session(scan_id)

        batch_a = [{"uid": f"uid_{i}"} for i in range(50)]
        batch_b = [{"uid": f"uid_{i}"} for i in range(25, 75)]

        results_a = []
        results_b = []

        def run_a():
            new, _meta = filter_seen(scan_id, batch_a)
            results_a.extend(result["uid"] for result in new)

        def run_b():
            new, _meta = filter_seen(scan_id, batch_b)
            results_b.extend(result["uid"] for result in new)

        thread_one = threading.Thread(target=run_a)
        thread_two = threading.Thread(target=run_b)
        thread_one.start()
        thread_two.start()
        thread_one.join()
        thread_two.join()

        all_uids = results_a + results_b
        assert len(all_uids) == len(set(all_uids))
        assert len(set(all_uids)) == 75

    def test_concurrent_flag_candidates_count(self):
        from src.scan_session import flag_candidates, get_session

        scan_id = "flag_test"
        get_session(scan_id)

        uids_a = [f"uid_{i}" for i in range(30)]
        uids_b = [f"uid_{i}" for i in range(15, 45)]

        added_counts = []

        def run_a():
            added, _total = flag_candidates(scan_id, uids_a, "label_a")
            added_counts.append(added)

        def run_b():
            added, _total = flag_candidates(scan_id, uids_b, "label_b")
            added_counts.append(added)

        thread_one = threading.Thread(target=run_a)
        thread_two = threading.Thread(target=run_b)
        thread_one.start()
        thread_two.start()
        thread_one.join()
        thread_two.join()

        session = get_session(scan_id)
        assert len(session.candidates) == 45

    def test_concurrent_get_candidates_during_flag(self):
        from src.scan_session import flag_candidates, get_candidates, get_session

        scan_id = "read_write_test"
        get_session(scan_id)

        errors: list[Exception] = []
        iterations = 50
        barrier = threading.Barrier(2)

        def writer():
            barrier.wait()
            for i in range(iterations):
                flag_candidates(scan_id, [f"uid_{i}"], label="test", phase=1)

        def reader():
            barrier.wait()
            try:
                for _ in range(iterations):
                    candidates = get_candidates(scan_id)
                    for candidate in candidates:
                        assert "uid" in candidate
                        assert "label" in candidate
            except Exception as exc:  # pragma: no cover - failure capture only
                errors.append(exc)

        thread_write = threading.Thread(target=writer)
        thread_read = threading.Thread(target=reader)
        thread_write.start()
        thread_read.start()
        thread_write.join()
        thread_read.join()

        assert not errors, f"get_candidates raised during concurrent mutation: {errors}"

    def test_concurrent_session_status_during_flag(self):
        from src.scan_session import flag_candidates, get_session, session_status

        scan_id = "status_write_test"
        get_session(scan_id)

        errors: list[Exception] = []
        iterations = 50
        barrier = threading.Barrier(2)

        def writer():
            barrier.wait()
            for i in range(iterations):
                flag_candidates(scan_id, [f"uid_{i}"], label="test", phase=1)

        def reader():
            barrier.wait()
            try:
                for _ in range(iterations):
                    status = session_status(scan_id)
                    assert status is not None
                    assert "seen_count" in status
                    assert "candidate_count" in status
            except Exception as exc:  # pragma: no cover - failure capture only
                errors.append(exc)

        thread_write = threading.Thread(target=writer)
        thread_read = threading.Thread(target=reader)
        thread_write.start()
        thread_read.start()
        thread_write.join()
        thread_read.join()

        assert not errors, f"session_status raised during concurrent mutation: {errors}"
