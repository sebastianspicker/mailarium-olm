from __future__ import annotations


def case_payload() -> dict[str, object]:
    return {
        "case_scope": {
            "target_person": {
                "name": "employee",
                "email": "employee@example.test",
                "role_hint": "employee",
            },
            "suspected_actors": [
                {
                    "name": "manager",
                    "email": "manager@example.test",
                    "role_hint": "manager",
                }
            ],
            "allegation_focus": ["retaliation", "exclusion"],
            "employment_issue_tags": ["sbv_participation"],
            "analysis_goal": "lawyer_briefing",
            "date_from": "2025-01-01",
            "date_to": "2025-06-30",
        },
        "source_scope": "emails_and_attachments",
        "include_message_appendix": True,
        "output_language": "en",
        "translation_mode": "translation_aware",
    }
