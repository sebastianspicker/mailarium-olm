"""Exchange Web Services transport implementation."""

from .gateway import EWSAttachment, EWSGateway, EWSItem, EWSItemRef, EWSOperationResult, EWSSyncDelta
from .transport import EWSHTTPSSession, EWSTransport

__all__ = [
    "EWSAttachment",
    "EWSGateway",
    "EWSHTTPSSession",
    "EWSItem",
    "EWSItemRef",
    "EWSOperationResult",
    "EWSSyncDelta",
    "EWSTransport",
]
