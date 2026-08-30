"""Composed proposal boundary for callers that need the full lifecycle."""

from __future__ import annotations

from .proposal_execution import MailboxProposalExecution
from .proposal_policy import MailboxProposalPolicy


class MailboxProposalService(MailboxProposalPolicy, MailboxProposalExecution):
    """Combine immutable proposal policy with remote execution mechanics."""
