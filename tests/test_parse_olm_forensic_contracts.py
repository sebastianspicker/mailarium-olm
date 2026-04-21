from src.parse_olm import Email


def test_to_dict_includes_forensic_fields():
    email = Email(
        message_id="forensic-1",
        subject="Forensic",
        sender_name="Alice",
        sender_email="employee@example.test",
        to=["bob@example.com"],
        cc=[],
        bcc=[],
        date="2025-01-01",
        body_text="Normalized body",
        body_html="<p>Normalized body</p>",
        folder="Inbox",
        has_attachments=False,
        raw_body_text="Raw text body",
        raw_body_html="<p>Raw html body</p>",
        raw_source="Subject: Forensic\n\nRaw source body",
        raw_source_headers={"Subject": "Forensic"},
        forensic_body_text="Raw text body",
        forensic_body_source="raw_body_text",
    )

    payload = email.to_dict()

    assert payload["raw_body_text"] == "Raw text body"
    assert payload["raw_body_html"] == "<p>Raw html body</p>"
    assert payload["raw_source"].startswith("Subject: Forensic")
    assert payload["raw_source_headers"] == {"Subject": "Forensic"}
    assert payload["forensic_body_text"] == "Raw text body"
    assert payload["forensic_body_source"] == "raw_body_text"
