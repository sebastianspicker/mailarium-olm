from __future__ import annotations

import sqlite3

from src.db_queries import QueryMixin


class _QueryHarness(QueryMixin):
    def __init__(self) -> None:
        self.conn = sqlite3.connect(":memory:")

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


def test_query_mixin_browse_family_delegates_to_extracted_helpers(monkeypatch):
    db = _QueryHarness()
    calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def fake_recipients_one(mixin, uid):
        calls.append(("recipients_one", (mixin, uid), {}))
        return {"to": [], "cc": [], "bcc": []}

    def fake_recipients_many(mixin, uids):
        calls.append(("recipients_many", (mixin, tuple(uids)), {}))
        return {}

    def fake_full(mixin, uid):
        calls.append(("full", (mixin, uid), {}))
        return {"uid": uid}

    def fake_batch(mixin, uids):
        calls.append(("batch", (mixin, tuple(uids)), {}))
        return {uid: {"uid": uid} for uid in uids}

    def fake_thread(mixin, conversation_id):
        calls.append(("thread", (mixin, conversation_id), {}))
        return []

    def fake_inferred(mixin, inferred_thread_id):
        calls.append(("inferred", (mixin, inferred_thread_id), {}))
        return []

    def fake_paginated(mixin, **kwargs):
        calls.append(("paginated", (mixin,), kwargs))
        return {"emails": [], "total": 0, "offset": kwargs["offset"], "limit": kwargs["limit"]}

    def fake_reembed(mixin, uid):
        calls.append(("reembed", (mixin, uid), {}))
        return {"uid": uid}

    monkeypatch.setattr("src.db_queries.recipients_for_uid_impl", fake_recipients_one)
    monkeypatch.setattr("src.db_queries.recipients_for_uids_impl", fake_recipients_many)
    monkeypatch.setattr("src.db_queries.get_email_full_impl", fake_full)
    monkeypatch.setattr("src.db_queries.get_emails_full_batch_impl", fake_batch)
    monkeypatch.setattr("src.db_queries.get_thread_emails_impl", fake_thread)
    monkeypatch.setattr("src.db_queries.get_inferred_thread_emails_impl", fake_inferred)
    monkeypatch.setattr("src.db_queries.list_emails_paginated_impl", fake_paginated)
    monkeypatch.setattr("src.db_queries.get_email_for_reembed_impl", fake_reembed)

    assert db._recipients_for_uid("uid-1") == {"to": [], "cc": [], "bcc": []}
    assert db._recipients_for_uids(["uid-1", "uid-2"]) == {}
    assert db.get_email_full("uid-1") == {"uid": "uid-1"}
    assert db.get_emails_full_batch(["uid-1"]) == {"uid-1": {"uid": "uid-1"}}
    assert db.get_thread_emails("conv-1") == []
    assert db.get_inferred_thread_emails("thread-1") == []
    assert db.list_emails_paginated(limit=5, offset=2)["limit"] == 5
    assert db.get_email_for_reembed("uid-1") == {"uid": "uid-1"}

    assert calls == [
        ("recipients_one", (db, "uid-1"), {}),
        ("recipients_many", (db, ("uid-1", "uid-2")), {}),
        ("full", (db, "uid-1"), {}),
        ("batch", (db, ("uid-1",)), {}),
        ("thread", (db, "conv-1"), {}),
        ("inferred", (db, "thread-1"), {}),
        (
            "paginated",
            (db,),
            {
                "offset": 2,
                "limit": 5,
                "sort_by": "date",
                "sort_order": "DESC",
                "folder": None,
                "sender": None,
                "category": None,
                "date_from": None,
                "date_to": None,
            },
        ),
        ("reembed", (db, "uid-1"), {}),
    ]
    db.close()
