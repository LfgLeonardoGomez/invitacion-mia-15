"""Small, single-process API protections; infrastructure limits remain mandatory."""

from __future__ import annotations

import json
import hashlib
import ipaddress
import logging
import math
import secrets
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Annotated, Callable

from fastapi import Header, HTTPException, Request, status
from starlette.types import ASGIApp, Message, Receive, Scope, Send


logger = logging.getLogger(__name__)
ADMIN_SESSION_COOKIE = "mia_admin_session"
ADMIN_SESSION_LIFETIME = 43_200


def admin_key(request: Request) -> str:
    settings = getattr(request.app.state, "settings", None)
    expected = getattr(settings, "admin_api_key", None)
    if not isinstance(expected, str) or len(expected) < 32:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Administración no disponible")
    return expected


def key_fingerprint(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def unauthorized() -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, "No autorizado", headers={"WWW-Authenticate": "Bearer"})


def validate_admin_origin(request: Request, *, required: bool = True, allow_same_origin_fetch: bool = False) -> None:
    origins = request.headers.getlist("origin")
    if not origins:
        if not required or (allow_same_origin_fetch and request.headers.get("sec-fetch-site") == "same-origin"):
            return
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Origen no permitido")
    configured = getattr(request.app.state.settings, "allowed_origins", ())
    same_origin = f"{request.url.scheme}://{request.url.netloc}"
    if len(origins) != 1 or origins[0] not in {*configured, same_origin}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Origen no permitido")


def local_session_cookie(request: Request) -> bool:
    """The only non-Secure exception is an explicitly local development request."""
    from urllib.parse import urlsplit
    origin = request.headers.get("origin", "")
    parsed = urlsplit(origin)
    if request.url.scheme != "http" or request.url.hostname not in {"localhost", "127.0.0.1", "::1"}:
        return False
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        return False
    try:
        return request.client is not None and ipaddress.ip_address(request.client.host).is_loopback
    except ValueError:
        return False


def require_admin_session(request: Request) -> dict[str, str]:
    expected = admin_key(request)
    # Reject ambiguous same-name cookies, including duplicate Cookie headers.
    values = [part.strip().split("=", 1)[1] for header in request.headers.getlist("cookie") for part in header.split(";") if part.strip().startswith(ADMIN_SESSION_COOKIE + "=")]
    store = getattr(request.app.state, "database", None)
    if len(values) != 1 or store is None:
        raise unauthorized()
    session = store.get_admin_session(values[0], key_fingerprint(expected))
    if session is None:
        raise unauthorized()
    validate_admin_origin(request, allow_same_origin_fetch=request.method in {"GET", "HEAD", "OPTIONS"})
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        supplied = request.headers.getlist("x-csrf-token")
        if len(supplied) != 1 or not secrets.compare_digest(supplied[0].encode("utf-8"), session["csrfToken"].encode("ascii")):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Solicitud no permitida")
    request.state.admin_session = session
    return session


def require_admin(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Fail closed if unconfigured; compare secret bytes, never echo credentials."""
    expected = admin_key(request)
    if not request.headers.getlist("authorization"):
        require_admin_session(request)
        return
    if len(request.headers.getlist("authorization")) != 1:
        raise unauthorized()
    if authorization is None or len(authorization) > 1024:
        raise unauthorized()
    scheme, separator, credential = authorization.partition(" ")
    if (
        scheme.lower() != "bearer"
        or not separator
        or not credential
        or credential != credential.strip()
        or any(character.isspace() for character in credential)
    ):
        raise unauthorized()
    # bytes comparison handles malformed/non-ASCII input without compare_digest's str restriction.
    supplied_bytes = credential.encode("utf-8")
    if len(supplied_bytes) > 1024 or not secrets.compare_digest(supplied_bytes, expected.encode("utf-8")):
        raise unauthorized()


def require_bootstrap_key(request: Request, authorization: Annotated[str | None, Header()] = None) -> None:
    if not request.headers.getlist("authorization"):
        admin_key(request)
        raise unauthorized()
    require_admin(request, authorization)
    validate_admin_origin(request, required=False)


@dataclass(slots=True)
class _Bucket:
    started_at: float
    last_seen: float
    count: int


class SecurityMiddleware:
    """Bounded buffering, coarse rate limits, and safe API response headers.

    Rate limits are process-local, not a distributed abuse-prevention service.
    No path tokens, headers, query strings, or body contents are stored in buckets.
    """

    def __init__(
        self,
        app: ASGIApp,
        max_body_bytes: int = 16_384,
        window_seconds: float = 60,
        public_limit: int = 120,
        rsvp_limit: int = 20,
        wish_limit: int = 10,
        admin_limit: int = 30,
        admin_read_limit: int | None = None,
        max_clients: int = 4096,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if min(max_body_bytes, public_limit, rsvp_limit, wish_limit, admin_limit, admin_limit if admin_read_limit is None else admin_read_limit, max_clients) < 1 or window_seconds <= 0:
            raise ValueError("Security limits must be positive")
        self.app = app
        self.max_body_bytes = max_body_bytes
        self.window_seconds = window_seconds
        self.limits = {"public": public_limit, "rsvp": rsvp_limit, "wish": wish_limit, "admin": admin_limit, "admin_read": admin_limit if admin_read_limit is None else admin_read_limit}
        self.max_clients = max_clients
        self.clock = clock
        self._buckets: OrderedDict[tuple[str, str], _Bucket] = OrderedDict()
        self._lock = threading.Lock()

    def _rate_limit(self, scope: Scope) -> int | None:
        path = scope.get("path", "")
        if path == "/api/admin" or path.startswith("/api/admin/"):
            category = "admin_read" if scope.get("method") in {"GET", "HEAD"} and path.rstrip("/") != "/api/admin/session" else "admin"
        elif scope.get("method") == "PUT" and path.startswith("/api/invitations/") and path.endswith("/rsvp"):
            category = "rsvp"
        elif scope.get("method") == "POST" and path.startswith("/api/invitations/") and path.endswith("/wishes"):
            category = "wish"
        else:
            category = "public"
        client = scope.get("client")
        key = (client[0] if client else "unknown", category)
        now = self.clock()
        with self._lock:
            # LRU order is last_seen order, so expired entries can be pruned from the front.
            while self._buckets:
                oldest_key, oldest = next(iter(self._buckets.items()))
                if now - oldest.last_seen < self.window_seconds:
                    break
                self._buckets.pop(oldest_key)
            bucket = self._buckets.get(key)
            if bucket is None or now - bucket.started_at >= self.window_seconds:
                bucket = _Bucket(now, now, 0)
                self._buckets[key] = bucket
            bucket.last_seen = now
            self._buckets.move_to_end(key)
            while len(self._buckets) > self.max_clients:
                self._buckets.popitem(last=False)
            if bucket.count >= self.limits[category]:
                return max(1, math.ceil(self.window_seconds - (now - bucket.started_at)))
            bucket.count += 1
        return None

    @staticmethod
    def _harden(message: Message) -> Message:
        protected = {
            b"x-content-type-options": b"nosniff",
            b"referrer-policy": b"no-referrer",
            b"cache-control": b"no-store",
            b"pragma": b"no-cache",
        }
        headers = [(key, value) for key, value in message.get("headers", []) if key.lower() not in protected]
        return {**message, "headers": headers + list(protected.items())}

    async def _error(self, send: Send, code: int, detail: str, extra_headers: list[tuple[bytes, bytes]] | None = None) -> None:
        body = json.dumps({"detail": detail}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = [(b"content-type", b"application/json; charset=utf-8"), (b"content-length", str(len(body)).encode("ascii"))]
        await send(self._harden({"type": "http.response.start", "status": code, "headers": headers + (extra_headers or [])}))
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] != "http" or not (path == "/api" or path.startswith("/api/")):
            await self.app(scope, receive, send)
            return

        response_started = False

        async def safe_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                message = self._harden(message)
            await send(message)

        # CORS middleware may handle preflight before us; passing OPTIONS through is safe.
        if scope.get("method") == "OPTIONS":
            await self.app(scope, receive, safe_send)
            return

        retry_after = self._rate_limit(scope)
        if retry_after is not None:
            await self._error(send, 429, "Demasiadas solicitudes", [(b"retry-after", str(retry_after).encode("ascii"))])
            return

        headers = scope.get("headers", [])
        lengths = [value for key, value in headers if key.lower() == b"content-length"]
        declared_length: int | None = None
        if lengths:
            if len(lengths) != 1 or not lengths[0].isdigit():
                await self._error(send, 400, "Solicitud inválida")
                return
            try:
                declared_length = int(lengths[0])
            except ValueError:
                await self._error(send, 400, "Solicitud inválida")
                return
            if declared_length > self.max_body_bytes:
                await self._error(send, 413, "Solicitud demasiado grande")
                return

        # Buffer only up to the cap, including requests without Content-Length.
        # The downstream app cannot mutate state before the whole request passed this check.
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > self.max_body_bytes:
                await self._error(send, 413, "Solicitud demasiado grande")
                return
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        if declared_length is not None and len(body) != declared_length:
            await self._error(send, 400, "Solicitud inválida")
            return

        if body and scope.get("method") in {"POST", "PUT", "PATCH", "DELETE"}:
            content_types = [value for key, value in headers if key.lower() == b"content-type"]
            encodings = [value for key, value in headers if key.lower() == b"content-encoding"]
            if (
                len(content_types) != 1
                or content_types[0].split(b";", 1)[0].strip().lower() != b"application/json"
                or any(value.strip().lower() != b"identity" for value in encodings)
            ):
                await self._error(send, 415, "Se requiere application/json")
                return

        replayed = False

        async def bounded_receive() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        try:
            await self.app(scope, bounded_receive, safe_send)
        except Exception as error:
            # Do not log exception messages/paths: they can contain family data or link tokens.
            logger.error("Unhandled API exception (%s)", type(error).__name__)
            if response_started:
                raise
            await self._error(send, 500, "Error interno")
