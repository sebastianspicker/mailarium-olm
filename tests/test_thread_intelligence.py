"""Tests for action item and decision extraction from email threads."""

from src.thread_intelligence import (
    ActionItem,
    Decision,
    ThreadAnalysis,
    ThreadAnalyzer,
)


class TestActionItemExtraction:
    def setup_method(self):
        self.analyzer = ThreadAnalyzer()

    def test_please_pattern(self):
        text = "Please review the attached document and provide feedback."
        items = self.analyzer.extract_action_items(text)
        assert len(items) >= 1
        assert any("review" in a.text.lower() for a in items)

    def test_need_to_pattern(self):
        text = "We need to finalize the budget report before the deadline."
        items = self.analyzer.extract_action_items(text)
        assert len(items) >= 1
        assert any("finalize" in a.text.lower() for a in items)

    def test_can_you_pattern(self):
        text = "Can you send me the latest version of the proposal document?"
        items = self.analyzer.extract_action_items(text)
        assert len(items) >= 1
        assert any("send" in a.text.lower() or "proposal" in a.text.lower() for a in items)

    def test_self_commitment_pattern(self):
        text = "I'll prepare the presentation slides by tomorrow."
        items = self.analyzer.extract_action_items(text, sender="alice@example.test")
        assert len(items) >= 1
        # Self-commitment: assignee should be the sender
        self_items = [a for a in items if a.assignee == "alice@example.test"]
        assert len(self_items) >= 1

    def test_action_required_pattern(self):
        text = "Action required: submit your timesheet by end of week."
        items = self.analyzer.extract_action_items(text)
        assert len(items) >= 1

    def test_urgency_detection(self):
        text = "This is urgent. Please complete the security review immediately."
        items = self.analyzer.extract_action_items(text)
        assert len(items) >= 1
        assert any(a.is_urgent for a in items)

    def test_deadline_detection(self):
        text = "Please submit the report by 03/15. We need it before the meeting."
        items = self.analyzer.extract_action_items(text)
        # Should detect deadline from "by 03/15"
        deadline_items = [a for a in items if a.deadline]
        assert len(items) >= 1, "Should extract at least one action item"
        assert len(deadline_items) >= 1, "Should detect deadline from 'by 03/15'"

    def test_empty_text(self):
        assert self.analyzer.extract_action_items("") == []
        assert self.analyzer.extract_action_items(None) == []

    def test_no_actions_in_text(self):
        text = "The weather is nice today. I had lunch at noon."
        items = self.analyzer.extract_action_items(text)
        assert len(items) == 0

    def test_deduplication(self):
        text = "Please review the document carefully. Please review the document carefully."
        items = self.analyzer.extract_action_items(text)
        texts = [a.text.lower().strip() for a in items]
        assert len(texts) == len(set(texts))

    def test_source_uid_preserved(self):
        text = "Please send me the updated contract for review."
        items = self.analyzer.extract_action_items(text, source_uid="uid-123")
        assert all(a.source_uid == "uid-123" for a in items)

    def test_follow_up_pattern(self):
        text = "Follow up: check with legal team about compliance requirements."
        items = self.analyzer.extract_action_items(text)
        assert len(items) >= 1

    def test_german_action_patterns(self):
        text = "Bitte prüfen Sie die Eingruppierung bis Freitag. Wir müssen die SBV heute noch informieren."
        items = self.analyzer.extract_action_items(text)
        assert len(items) >= 1
        assert any("eingruppierung" in a.text.lower() or "sbv" in a.text.lower() for a in items)


class TestDecisionExtraction:
    def setup_method(self):
        self.analyzer = ThreadAnalyzer()

    def test_we_decided_pattern(self):
        text = "We decided to postpone the launch until next quarter."
        decisions = self.analyzer.extract_decisions(text)
        assert len(decisions) >= 1
        assert any("postpone" in d.text.lower() for d in decisions)

    def test_agreed_to_pattern(self):
        text = "The team agreed to use the new framework for development."
        decisions = self.analyzer.extract_decisions(text)
        assert len(decisions) >= 1

    def test_confirmed_pattern(self):
        text = "Management confirmed that the budget increase was approved."
        decisions = self.analyzer.extract_decisions(text)
        assert len(decisions) >= 1

    def test_approved_pattern(self):
        text = "The proposal was approved by the steering committee today."
        decisions = self.analyzer.extract_decisions(text)
        assert len(decisions) >= 1

    def test_proceed_with_pattern(self):
        text = "We will proceed with the vendor selection as discussed earlier."
        decisions = self.analyzer.extract_decisions(text)
        assert len(decisions) >= 1

    def test_go_ahead_pattern(self):
        text = "Let's go with option B for the database migration plan."
        decisions = self.analyzer.extract_decisions(text)
        assert len(decisions) >= 1

    def test_german_decision_patterns(self):
        text = "Wir haben entschieden, die mobile Arbeit vorerst fortzuführen. Die Entscheidung ist damit bestätigt."
        decisions = self.analyzer.extract_decisions(text)
        assert len(decisions) >= 1

    def test_empty_text(self):
        assert self.analyzer.extract_decisions("") == []
        assert self.analyzer.extract_decisions(None) == []

    def test_no_decisions_in_text(self):
        text = "The weather is nice today. I had lunch at noon."
        decisions = self.analyzer.extract_decisions(text)
        assert len(decisions) == 0

    def test_sender_and_date_preserved(self):
        text = "We decided to go ahead with the merger and acquisitions plan."
        decisions = self.analyzer.extract_decisions(text, sender="boss@example.test", date="2024-01-15", source_uid="uid-456")
        for d in decisions:
            assert d.made_by == "boss@example.test"
            assert d.date == "2024-01-15"
            assert d.source_uid == "uid-456"

    def test_deduplication(self):
        text = "We decided to go with option A for now. Later, we decided to go with option A for now."
        decisions = self.analyzer.extract_decisions(text)
        texts = [d.text.lower().strip() for d in decisions]
        assert len(texts) == len(set(texts))


class TestThreadAnalyzer:
    def setup_method(self):
        self.analyzer = ThreadAnalyzer()

    def test_analyze_empty_thread(self):
        result = self.analyzer.analyze_thread([])
        assert isinstance(result, ThreadAnalysis)
        assert result.summary == ""
        assert result.action_items == []
        assert result.decisions == []
        assert result.participants == []

    def test_analyze_thread_with_actions_and_decisions(self):
        emails = [
            {
                "clean_body": "We need to finalize the project plan. Please review the timeline and provide feedback.",
                "sender_name": "Alice",
                "sender_email": "alice@example.test",
                "date": "2024-01-10",
                "uid": "uid-1",
                "subject": "Project Plan",
            },
            {
                "clean_body": "We decided to extend the deadline by two weeks. I'll update the Gantt chart accordingly.",
                "sender_name": "Bob",
                "sender_email": "bob@example.test",
                "date": "2024-01-11",
                "uid": "uid-2",
                "subject": "Re: Project Plan",
            },
        ]
        result = self.analyzer.analyze_thread(emails)
        assert result.summary != ""
        assert len(result.action_items) >= 1
        assert len(result.decisions) >= 1

    def test_participants_identified(self):
        emails = [
            {"clean_body": "Starting the thread.", "sender_email": "alice@example.test", "sender_name": "Alice"},
            {"clean_body": "Replying here.", "sender_email": "bob@example.test", "sender_name": "Bob"},
            {"clean_body": "Me too.", "sender_email": "alice@example.test", "sender_name": "Alice"},
        ]
        result = self.analyzer.analyze_thread(emails)
        assert len(result.participants) == 2
        # Alice sent 2, Bob sent 1
        alice = next(p for p in result.participants if p["email"] == "alice@example.test")
        assert alice["message_count"] == 2
        assert alice["role"] == "initiator"
        bob = next(p for p in result.participants if p["email"] == "bob@example.test")
        assert bob["message_count"] == 1
        assert bob["role"] == "responder"

    def test_to_dict(self):
        analysis = ThreadAnalysis(
            summary="Test summary here.",
            action_items=[ActionItem(text="do X", assignee="alice", is_urgent=True)],
            decisions=[Decision(text="go with Y", made_by="bob", date="2024-01-15")],
            participants=[{"email": "alice@example.test", "message_count": 3, "role": "initiator"}],
        )
        d = analysis.to_dict()
        assert d["summary"] == "Test summary here."
        assert len(d["action_items"]) == 1
        assert d["action_items"][0]["text"] == "do X"
        assert d["action_items"][0]["is_urgent"] is True
        assert len(d["decisions"]) == 1
        assert d["decisions"][0]["made_by"] == "bob"
        assert len(d["participants"]) == 1


class TestMCPThreadTools:
    def test_thread_summary_tool_importable(self):
        from src.tools import threads

        assert callable(threads.register)

    def test_action_items_tool_importable(self):
        from src.tools import threads

        assert callable(threads.register)

    def test_decisions_tool_importable(self):
        from src.tools import threads

        assert callable(threads.register)

    def test_thread_summary_input(self):
        from src.mcp_models import ThreadSummaryInput

        inp = ThreadSummaryInput(conversation_id="test-thread-123", max_sentences=3)
        assert inp.conversation_id == "test-thread-123"
        assert inp.max_sentences == 3

    def test_action_items_input(self):
        from src.mcp_models import ActionItemsInput

        inp = ActionItemsInput(conversation_id="abc", days=7, limit=10)
        assert inp.conversation_id == "abc"
        assert inp.days == 7
        assert inp.limit == 10

    def test_decisions_input(self):
        from src.mcp_models import DecisionsInput

        inp = DecisionsInput(conversation_id="xyz", days=30)
        assert inp.conversation_id == "xyz"
        assert inp.days == 30


class TestUrgencyScopeOnActionText:
    """Urgency should be checked against action item text, not the full email body."""

    def test_urgency_only_on_matching_item(self):
        from src.thread_intelligence import ThreadAnalyzer

        ta = ThreadAnalyzer()
        body = "Please update the style guide for the website. Also, we need to finalize the budget ASAP."
        items = ta.extract_action_items(body)
        # If any items found, urgency should only apply to the ASAP item
        for it in items:
            if "asap" in it.text.lower() or "budget" in it.text.lower():
                # This item mentions ASAP, may be urgent
                pass
            else:
                # Items not mentioning urgency words should NOT be urgent
                assert not it.is_urgent, f"Non-urgent text marked urgent: {it.text}"
