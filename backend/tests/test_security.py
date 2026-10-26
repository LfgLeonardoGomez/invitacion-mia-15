"""Security component tests independent from the invitation persistence layer."""

from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from backend.app.security import SecurityMiddleware, require_admin


KEY = "only-for-tests-" + "x" * 32


def make_app(key=KEY, **limits):
    app = FastAPI()
    app.state.settings = SimpleNamespace(admin_api_key=key)
    app.add_middleware(SecurityMiddleware, **limits)

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/api/admin/event")
    def admin(_: Annotated[None, Depends(require_admin)]):
        return {"ok": True}

    @app.post("/api/admin/rotate")
    def rotate(_: Annotated[None, Depends(require_admin)]):
        return {"ok": True}

    @app.put("/api/invitations/test-token/rsvp")
    async def rsvp(request: Request):
        return await request.json()

    @app.get("/api/crash")
    def crash():
        raise ValueError("sensitive-link-token-do-not-expose")

    return app


def assert_headers(response):
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"


def test_configured_admin_requires_exact_key():
    with TestClient(make_app()) as client:
        response = client.get("/api/admin/event", headers={"Authorization": f"Bearer {KEY}"})
        assert response.status_code == 200
        assert_headers(response)
        assert client.get("/api/admin/event", headers={"Authorization": f"bEaReR {KEY}"}).status_code == 200


@pytest.mark.parametrize("value", [None, "", "Bearer", "Basic abc", "Bearer ", "Bearer wrong", "Bearer " + KEY + " ", "Bearer  " + KEY, "Bearer " + "x" * 1100])
def test_auth_malformed_and_wrong_is_generic_401(value):
    with TestClient(make_app()) as client:
        headers = {} if value is None else {"Authorization": value}
        response = client.get("/api/admin/event", headers=headers)
        assert response.status_code == 401
        assert response.json() == {"detail": "No autorizado"}
        assert response.headers["www-authenticate"] == "Bearer"
        assert KEY not in response.text
        assert_headers(response)


def test_non_ascii_and_duplicate_credentials_do_not_cause_500():
    with TestClient(make_app()) as client:
        unicode_response = client.get("/api/admin/event", headers=[(b"authorization", "Bearer contraseña".encode("utf-8"))])
        assert unicode_response.status_code == 401
        duplicate_response = client.get("/api/admin/event", headers=[("authorization", f"Bearer {KEY}"), ("authorization", f"Bearer {KEY}")])
        assert duplicate_response.status_code == 401


@pytest.mark.parametrize("key", [None, "", "too-short"])
def test_unconfigured_or_invalid_admin_is_disabled(key):
    with TestClient(make_app(key)) as client:
        response = client.get("/api/admin/event", headers={"Authorization": f"Bearer {KEY}"})
        assert response.status_code == 503
        assert_headers(response)
        assert client.get("/api/health").status_code == 200


def test_empty_rotation_post_does_not_require_json_header():
    with TestClient(make_app()) as client:
        assert client.post("/api/admin/rotate", headers={"Authorization": f"Bearer {KEY}"}).status_code == 200


@pytest.mark.parametrize("content_type", [None, "text/plain", "application/x-www-form-urlencoded", "application/json, text/plain"])
def test_non_json_write_rejected(content_type):
    with TestClient(make_app()) as client:
        headers = {} if content_type is None else {"Content-Type": content_type}
        response = client.put("/api/invitations/test-token/rsvp", content=b'{"guestCount":1}', headers=headers)
        assert response.status_code == 415
        assert_headers(response)


def test_json_charset_accepted_and_compressed_body_rejected():
    with TestClient(make_app()) as client:
        response = client.put("/api/invitations/test-token/rsvp", content=b'{"guestCount":1}', headers={"Content-Type": "application/json; charset=utf-8"})
        assert response.status_code == 200
        response = client.put("/api/invitations/test-token/rsvp", content=b'{}', headers={"Content-Type": "application/json", "Content-Encoding": "gzip"})
        assert response.status_code == 415


def asgi_call(app, *, path="/api/health", method="GET", headers=None, chunks=None, client="192.0.2.1"):
    messages = list(chunks or [{"type": "http.request", "body": b"", "more_body": False}])
    sent = []
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": method, "path": path, "raw_path": path.encode(), "query_string": b"",
        "scheme": "http", "server": ("testserver", 80), "client": (client, 123), "headers": headers or [],
    }

    async def receive():
        return messages.pop(0) if messages else {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    asyncio.run(app(scope, receive, send))
    start = next(message for message in sent if message["type"] == "http.response.start")
    body = b"".join(message.get("body", b"") for message in sent if message["type"] == "http.response.body")
    return start["status"], dict(start.get("headers", [])), body


def tiny_app(calls):
    async def app(scope, receive, send):
        calls.append(scope["path"])
        body = await receive()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": body.get("body", b"")})
    return app


def test_declared_and_chunked_limits_before_downstream_mutation():
    calls = []
    middleware = SecurityMiddleware(tiny_app(calls), max_body_bytes=8)
    status_code, headers, _ = asgi_call(middleware, method="PUT", headers=[(b"content-length", b"9")])
    assert status_code == 413 and not calls
    assert headers[b"cache-control"] == b"no-store"
    status_code, _, _ = asgi_call(middleware, method="PUT", headers=[(b"content-type", b"application/json")], chunks=[
        {"type": "http.request", "body": b"12345", "more_body": True},
        {"type": "http.request", "body": b"6789", "more_body": False},
    ])
    assert status_code == 413 and not calls
    status_code, _, body = asgi_call(middleware, method="PUT", headers=[(b"content-type", b"application/json")], chunks=[
        {"type": "http.request", "body": b"1234", "more_body": True},
        {"type": "http.request", "body": b"5678", "more_body": False},
    ])
    assert status_code == 200 and body == b"12345678" and len(calls) == 1


@pytest.mark.parametrize("headers", [[(b"content-length", b"-1")], [(b"content-length", b"abc")], [(b"content-length", b"0"), (b"content-length", b"0")], [(b"content-length", b"1")]])
def test_ambiguous_or_mismatched_lengths_rejected(headers):
    calls = []
    status_code, _, _ = asgi_call(SecurityMiddleware(tiny_app(calls)), headers=headers)
    assert status_code == 400 and not calls


def test_rates_use_real_peer_not_forwarded_headers_and_expire():
    clock = [10.0]
    middleware = SecurityMiddleware(tiny_app([]), public_limit=2, window_seconds=60, clock=lambda: clock[0])
    assert asgi_call(middleware)[0] == 200
    assert asgi_call(middleware, headers=[(b"x-forwarded-for", b"192.0.2.222")])[0] == 200
    status_code, headers, _ = asgi_call(middleware, headers=[(b"x-forwarded-for", b"192.0.2.223")])
    assert status_code == 429 and headers[b"retry-after"] == b"60"
    assert asgi_call(middleware, client="192.0.2.2")[0] == 200
    clock[0] += 61
    assert asgi_call(middleware)[0] == 200


def test_separate_categories_and_no_raw_tokens_in_buckets():
    middleware = SecurityMiddleware(tiny_app([]), public_limit=1, rsvp_limit=1, admin_limit=1)
    assert asgi_call(middleware)[0] == 200
    assert asgi_call(middleware)[0] == 429
    assert asgi_call(middleware, path="/api/invitations/raw-secret-token/rsvp", method="PUT")[0] == 200
    assert asgi_call(middleware, path="/api/invitations/another-secret-token/rsvp", method="PUT")[0] == 429
    assert asgi_call(middleware, path="/api/admin/event")[0] == 200
    assert asgi_call(middleware, path="/api/admin/event")[0] == 429
    assert "secret-token" not in repr(middleware._buckets)


def test_rate_cache_bounded_and_thread_safe():
    middleware = SecurityMiddleware(tiny_app([]), max_clients=4, public_limit=3)
    for number in range(12):
        asgi_call(middleware, client=f"192.0.2.{number}")
    assert len(middleware._buckets) == 4
    fresh = SecurityMiddleware(tiny_app([]), public_limit=5)
    with ThreadPoolExecutor(max_workers=12) as pool:
        statuses = list(pool.map(lambda _: asgi_call(fresh)[0], range(20)))
    assert statuses.count(200) == 5
    assert statuses.count(429) == 15


def test_options_not_rate_limited_and_cors_preflight_works():
    app = make_app(public_limit=1, admin_limit=1)
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["GET", "PUT"], allow_headers=["Authorization", "Content-Type"])
    with TestClient(app) as client:
        for _ in range(3):
            response = client.options("/api/admin/event", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "PUT", "Access-Control-Request-Headers": "Authorization,Content-Type"})
            assert response.status_code == 200
            assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/health").status_code == 429


def test_unhandled_errors_generic_and_no_sensitive_message_in_logs(caplog):
    with TestClient(make_app(), raise_server_exceptions=False) as client:
        response = client.get("/api/crash")
        assert response.status_code == 500
        assert response.json() == {"detail": "Error interno"}
        assert_headers(response)
    assert "sensitive-link-token" not in caplog.text


def test_headers_on_not_found_and_public_validation_errors():
    with TestClient(make_app()) as client:
        response = client.get("/api/missing")
        assert response.status_code == 404
        assert_headers(response)


@pytest.mark.parametrize("kwargs", [{"max_body_bytes": 0}, {"window_seconds": 0}, {"max_clients": 0}, {"public_limit": -1}])
def test_invalid_limits_rejected(kwargs):
    with pytest.raises(ValueError):
        SecurityMiddleware(tiny_app([]), **kwargs)


def test_real_api_rejections_keep_private_headers_and_allowed_cors(tmp_path):
    from backend.app.config import Settings
    from backend.app.main import create_app

    origin = "https://invite.example"
    app = create_app(Settings(database_path=tmp_path / "integration.sqlite3", admin_api_key="integration-test-key-01234567890123456789", allowed_origins=(origin,)))
    with TestClient(app) as client:
        responses = [
            client.get("/api/admin/event", headers={"Origin": origin}),
            client.get("/api/invitations/invalid", headers={"Origin": origin}),
            client.put("/api/invitations/invalid/rsvp", json={"attending": "true", "guestCount": 1}, headers={"Origin": origin}),
            client.post("/api/admin/invitations", content="{}", headers={"Origin": origin, "Content-Type": "text/plain"}),
            client.post("/api/admin/invitations", content=b"x" * 16_385, headers={"Origin": origin, "Content-Type": "application/json"}),
        ]
        assert [response.status_code for response in responses] == [401, 404, 422, 415, 413]
        for response in responses:
            assert_headers(response)
            assert response.headers["access-control-allow-origin"] == origin
        # Default public limit includes the earlier 404; admin/RSVP requests use separate quotas.
        for _ in range(119):
            assert client.get("/api/health").status_code == 200
        limited = client.get("/api/health", headers={"Origin": origin})
        assert limited.status_code == 429
        assert int(limited.headers["retry-after"]) > 0
        assert limited.headers["access-control-allow-origin"] == origin
        assert_headers(limited)


def test_real_api_database_error_does_not_expose_private_details(tmp_path, monkeypatch, caplog):
    import sqlite3

    from backend.app.config import Settings
    from backend.app.main import create_app

    key = "integration-test-key-01234567890123456789"
    app = create_app(Settings(database_path=tmp_path / "integration.sqlite3", admin_api_key=key))

    def unavailable():
        raise sqlite3.OperationalError("private-path-family-secret-token")

    with TestClient(app) as client:
        monkeypatch.setattr(app.state.database, "get_event", unavailable)
        response = client.get("/api/admin/event", headers={"Authorization": f"Bearer {key}"})
        assert response.status_code == 503
        assert_headers(response)
        assert "private-path-family-secret-token" not in response.text
        assert "private-path-family-secret-token" not in caplog.text
