"""Dossier evidence-rendering tests."""

from __future__ import annotations

pytest_plugins = ["tests._dossier_cases"]


def test_generate_includes_evidence_items(gen):
    result = gen.generate()

    assert result["evidence_count"] == 3
    assert "harassment" in result["html"]
    assert "discrimination" in result["html"]


def test_generate_includes_source_emails(gen):
    result = gen.generate()

    assert result["email_count"] == 3
    assert "Source Email Appendix" in result["html"]
    assert "uid-1" in result["html"]


def test_dotted_conditionals_in_loop(gen):
    result = gen.generate()
    html = result["html"]

    assert "<strong>To:</strong>" in html
    assert "{% if email.to %}" not in html


def test_dotted_conditional_false_branch(gen):
    result = gen.generate()
    html = result["html"]

    assert "<strong>CC:</strong>" not in html
    assert "{% if email.cc %}" not in html


def test_evidence_numbering(gen):
    result = gen.generate()
    html = result["html"]

    assert "E-1" in html
    assert "E-2" in html
    assert "E-3" in html


def test_appendix_numbering(gen):
    result = gen.generate()
    html = result["html"]

    assert "A-1" in html
    assert "A-2" in html
    assert "A-3" in html


def test_cross_references(gen):
    result = gen.generate()
    html = result["html"]

    assert "Appendix" in html
    assert "#appendix-A-" in html


def test_evidence_quote_banner(gen):
    result = gen.generate()
    html = result["html"]

    assert "evidence-quote-banner" in html
    assert "evidence content" in html


def test_attachment_info_in_appendix(db, gen):
    db.conn.execute(
        "INSERT INTO attachments (email_uid, name, mime_type, size) VALUES (?, ?, ?, ?)",
        ("uid-1", "report.pdf", "application/pdf", 12345),
    )
    db.conn.commit()

    result = gen.generate()
    html = result["html"]

    assert "report.pdf" in html
    assert "attachment-bar" in html


def test_no_attachment_bar_when_none(gen):
    result = gen.generate()
    html = result["html"]

    assert '<div class="attachment-bar">' not in html


def test_thread_topic_shown(db, gen):
    db.conn.execute(
        "UPDATE emails SET thread_topic = ? WHERE uid = ?",
        ("Budget Discussion", "uid-1"),
    )
    db.conn.commit()

    result = gen.generate()
    html = result["html"]

    assert "Budget Discussion" in html
    assert "<strong>Thread:</strong>" in html


def test_notes_hidden_when_empty(gen):
    result = gen.generate()
    html = result["html"]

    assert "<strong>Notes:</strong>" not in html


def test_notes_shown_when_present(db, gen):
    db.conn.execute(
        "UPDATE evidence_items SET notes = ? WHERE id = 1",
        ("Important context about this incident.",),
    )
    db.conn.commit()

    result = gen.generate()
    html = result["html"]

    assert "Important context about this incident." in html
    assert "<strong>Notes:</strong>" in html


def test_verification_banner_all_verified(gen):
    result = gen.generate()
    html = result["html"]

    assert "banner-ok" in html or "banner-warn" in html
    assert "verification-banner" in html


def test_verification_banner_partial(db, gen):
    db.add_evidence("uid-1", "general", "nonexistent quote xyz", "Unverifiable", 2)
    result = gen.generate()
    html = result["html"]

    assert "banner-warn" in html
    assert "unverified" in html.lower()


def test_evidence_index_table(gen):
    result = gen.generate()
    html = result["html"]

    assert "Index of Evidence" in html
    assert "evidence-index-table" in html
    assert "E-1" in html


def test_toc_includes_index(gen):
    result = gen.generate()
    html = result["html"]

    assert "#evidence-index" in html


def test_bcc_shown_in_appendix(db, gen):
    db.conn.execute(
        "INSERT INTO recipients(email_uid, address, display_name, type) VALUES(?,?,?,?)",
        ("uid-1", "secret@example.test", "Secret Person", "bcc"),
    )
    db.conn.commit()

    result = gen.generate()
    html = result["html"]

    assert "secret@example.test" in html
    assert "<strong>BCC:</strong>" in html


def test_folder_shown_in_appendix(db, gen):
    db.conn.execute(
        "UPDATE emails SET folder = ? WHERE uid = ?",
        ("Inbox/Important", "uid-1"),
    )
    db.conn.commit()

    result = gen.generate()
    html = result["html"]

    assert "Inbox/Important" in html
    assert "<strong>Folder:</strong>" in html


def test_attachment_details_shown(db, gen):
    db.conn.execute(
        "INSERT INTO attachments (email_uid, name, mime_type, size) VALUES (?, ?, ?, ?)",
        ("uid-1", "contract.pdf", "application/pdf", 1048576),
    )
    db.conn.commit()

    result = gen.generate()
    html = result["html"]

    assert "contract.pdf" in html
    assert "application/pdf" in html
    assert "1.0 MB" in html


def test_updated_at_shown_when_different(db, gen):
    db.conn.execute(
        "UPDATE evidence_items SET updated_at = ? WHERE id = 1",
        ("2024-06-15T10:00:00",),
    )
    db.conn.commit()

    result = gen.generate()
    html = result["html"]

    assert "<strong>Updated:</strong>" in html
