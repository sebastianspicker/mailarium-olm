"""HTTPS-only EWS transport with redacted diagnostics."""

from __future__ import annotations

from base64 import b64encode
from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module
from typing import Any
from urllib import error, request
from urllib.parse import urlparse

from .errors import EWSAuthenticationError, EWSConfigurationError, EWSHTTPError, EWSValidationError


def basic_authorization(username: str, password: str) -> str:
    """Build a Basic header without retaining credentials in transport state."""
    if not username or not password:
        raise EWSConfigurationError("EWS basic credentials are required")
    token = b64encode(f"{username}:{password}".encode()).decode("ascii")
    return f"Basic {token}"


@dataclass(frozen=True)
class EWSHTTPSSession:
    """Stdlib HTTPS session factory; NTLM loads its optional client lazily."""

    authorization: str | None = None
    ntlm_username: str | None = None
    ntlm_password: str | None = None

    def preflight(self) -> None:
        """Validate optional authentication dependencies before a remote claim."""
        if self.ntlm_username is None and self.ntlm_password is None:
            return
        if not self.ntlm_username or not self.ntlm_password:
            raise EWSConfigurationError("both NTLM username and password are required")
        try:
            import_module("requests")
            import_module("requests_ntlm")
        except ImportError as exc:  # pragma: no cover - optional dependency boundary
            raise EWSConfigurationError("NTLM requires the ews-ntlm extra") from exc

    def __call__(self) -> Any:
        if self.ntlm_username is None and self.ntlm_password is None:
            return _UrllibSession(self.authorization)
        self.preflight()
        try:
            requests = import_module("requests")
            HttpNtlmAuth = import_module("requests_ntlm").HttpNtlmAuth
        except ImportError as exc:  # pragma: no cover - optional dependency boundary
            raise EWSConfigurationError("NTLM requires the ews-ntlm extra") from exc
        session = requests.Session()
        if self.authorization:
            session.headers["Authorization"] = self.authorization
        session.auth = HttpNtlmAuth(self.ntlm_username, self.ntlm_password)
        return _RequestsSession(session)


@dataclass(frozen=True)
class _BufferedResponse:
    status_code: int
    content: bytes


class _UrllibSession:
    def __init__(self, authorization: str | None) -> None:
        self.authorization = authorization
        self.opener = request.build_opener(_RejectRedirects())

    def post(
        self,
        url: str,
        *,
        data: bytes,
        headers: dict[str, str],
        timeout: float,
        max_response_bytes: int,
    ) -> _BufferedResponse:
        outbound_headers = dict(headers)
        if self.authorization:
            outbound_headers["Authorization"] = self.authorization
        outbound = request.Request(url, data=data, headers=outbound_headers, method="POST")
        try:
            with self.opener.open(outbound, timeout=timeout) as raw:  # nosec B310
                return _buffered_urllib_response(raw, max_response_bytes)
        except error.HTTPError as exc:
            return _buffered_urllib_response(exc, max_response_bytes)

    def close(self) -> None:
        return None


class _RejectRedirects(request.HTTPRedirectHandler):
    """Return redirects as HTTP errors so credentials never follow them."""

    def redirect_request(
        self,
        req: Any,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


class _RequestsSession:
    """Bounded requests adapter used only by the optional NTLM profile."""

    def __init__(self, session: Any) -> None:
        self.session = session

    def post(
        self,
        url: str,
        *,
        data: bytes,
        headers: dict[str, str],
        timeout: float,
        max_response_bytes: int,
    ) -> _BufferedResponse:
        response = self.session.post(
            url,
            data=data,
            headers=headers,
            timeout=timeout,
            allow_redirects=False,
            stream=True,
        )
        try:
            content = bytearray()
            for chunk in response.iter_content(chunk_size=64 * 1024):
                content.extend(chunk)
                if len(content) > max_response_bytes:
                    break
            return _BufferedResponse(int(response.status_code), bytes(content))
        finally:
            response.close()

    def close(self) -> None:
        self.session.close()


def _buffered_urllib_response(raw: Any, max_response_bytes: int) -> _BufferedResponse:
    status_code = getattr(raw, "status", None)
    resolved_status = int(status_code if status_code is not None else raw.getcode())
    return _BufferedResponse(resolved_status, raw.read(max_response_bytes + 1))


DebugSink = Callable[[dict[str, object]], None]


class EWSTransport:
    """Posts SOAP envelopes over HTTPS and never emits SOAP bodies to diagnostics."""

    def __init__(
        self,
        endpoint: str,
        session_factory: Callable[[], Any],
        *,
        timeout_seconds: float = 30.0,
        max_response_bytes: int = 10_000_000,
        debug_sink: DebugSink | None = None,
    ) -> None:
        """Configure an HTTPS-only SOAP transport with bounded response handling."""
        parsed = urlparse(endpoint)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise EWSConfigurationError("EWS endpoint must be an absolute HTTPS URL without credentials, query, or fragment")
        if timeout_seconds <= 0:
            raise EWSConfigurationError("EWS timeout must be positive")
        if max_response_bytes < 1:
            raise EWSConfigurationError("EWS response limit must be positive")
        self.endpoint = endpoint
        self.session_factory = session_factory
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.debug_sink = debug_sink

    def execute(self, operation: str, envelope: bytes) -> bytes:
        """Post one SOAP envelope and classify HTTP failures without logging its body."""
        if not operation or not envelope:
            raise EWSValidationError("EWS operation and SOAP envelope are required")
        session = self.session_factory()
        try:
            response = session.post(
                self.endpoint,
                data=envelope,
                headers={
                    "Content-Type": "text/xml; charset=utf-8",
                    "SOAPAction": f"http://schemas.microsoft.com/exchange/services/2006/messages/{operation}",
                },
                timeout=self.timeout_seconds,
                max_response_bytes=self.max_response_bytes,
            )
            body = bytes(response.content)
            if len(body) > self.max_response_bytes:
                raise EWSValidationError("EWS response exceeds configured size limit")
            status_code = int(response.status_code)
            self._diagnose(operation, status_code, len(envelope), len(body))
            if status_code in {401, 403}:
                raise EWSAuthenticationError(f"EWS HTTP {status_code}")
            if 300 <= status_code < 400:
                raise EWSValidationError("EWS redirects are not allowed")
            # Exchange commonly carries a structured EWS response or SOAP
            # fault in an HTTP 4xx/5xx body. Preserve that body so the gateway
            # can classify conflict, retry, expired-watermark, and ambiguous
            # write outcomes from the protocol response instead of collapsing
            # every post-send failure into a local validation error.
            if status_code >= 400:
                raise EWSHTTPError(status_code, body)
            return body
        finally:
            close = getattr(session, "close", None)
            if callable(close):
                close()

    def _diagnose(self, operation: str, status_code: int, request_size: int, response_size: int) -> None:
        if self.debug_sink is not None:
            self.debug_sink(
                {
                    "host": urlparse(self.endpoint).hostname or "",
                    "operation": operation,
                    "status_code": status_code,
                    "request_size": request_size,
                    "response_size": response_size,
                }
            )
