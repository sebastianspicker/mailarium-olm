from src.parse_olm import Email


def make_email(*, subject: str, sender_email: str, body_text: str, has_attachments: bool = False) -> Email:
    return Email(
        message_id=f"<{subject}-{sender_email}>",
        subject=subject,
        sender_name=sender_email.split("@", 1)[0].title(),
        sender_email=sender_email,
        to=["team@example.com"],
        cc=[],
        bcc=[],
        date="2026-04-10T10:00:00Z",
        body_text=body_text,
        body_html="",
        folder="Inbox",
        has_attachments=has_attachments,
        attachment_names=["budget.xlsx"] if has_attachments else [],
        attachments=(
            [{"name": "budget.xlsx", "mime_type": "application/vnd.ms-excel", "size": 1234, "content_id": "", "is_inline": False}]
            if has_attachments
            else []
        ),
    )
