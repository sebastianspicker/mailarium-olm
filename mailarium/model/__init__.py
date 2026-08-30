"""Durable mailbox domain models."""

from .chunks import EmailChunk
from .message import (
    MESSAGE_UID_ALGORITHM,
    MESSAGE_UID_VERSION,
    Message,
    canonical_message_uid,
    classify_message_type,
)

__all__ = [
    "MESSAGE_UID_ALGORITHM",
    "MESSAGE_UID_VERSION",
    "EmailChunk",
    "Message",
    "canonical_message_uid",
    "classify_message_type",
]
