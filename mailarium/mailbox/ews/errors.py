"""Exceptions raised by the compact EWS transport."""


class EWSError(Exception):
    """Base class for EWS transport failures."""


class EWSConfigurationError(EWSError):
    """Raised for unsafe or incomplete local configuration."""


class EWSAuthenticationError(EWSError):
    """Raised when Exchange rejects authentication."""


class EWSHTTPError(EWSError):
    """Carry a bounded non-success HTTP response to the SOAP parser without logging its body."""

    def __init__(self, status_code: int, body: bytes) -> None:
        super().__init__(f"EWS HTTP {status_code}")
        self.status_code = status_code
        self.body = bytes(body)


class EWSFaultError(EWSError):
    """A SOAP fault or non-success EWS response."""

    def __init__(self, code: str, message: str, *, http_status: int | None = None) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.http_status = http_status


class EWSValidationError(EWSError):
    """Raised before a malformed or unsafe SOAP request is sent."""
