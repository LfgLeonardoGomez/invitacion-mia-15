"""Cookie sessions never persist the administrative key in browser-readable storage."""

import hashlib
import sqlite3
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.database import Database
from backend.app.main import create_app
from backend.app.security import ADMIN_SESSION_COOKIE, key_fingerprint
from backend.tests.keys import TEST_LINK_KEY


KEY = "only-for-local-tests-" + "x" * 32
ORIGIN = "https://panel.example.test"
AUTH = {"Authorization": f"Bearer {KEY}", "Origin": ORIGIN}


@pytest.fixture
def settings(tmp_path):
    return Settings(database_path=tmp_path / "private" / "sessions.sqlite3", admin_api_key=KEY, allowed_origins=(ORIGIN, "http://127.0.0.1:5173"), link_encryption_key=TEST_LINK_KEY)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings), base_url="https://api.example.test") as current:
        yield current


def login(client):
    response = client.post("/api/admin/session", headers=AUTH)
    assert response.status_code == 200
    result = response.json()
    assert set(result) == {"authenticated", "csrfToken", "expiresAt"}
    assert result["authenticated"] is True
    return response, result


def test_login_flags_hash_only_restore_and_no_admin_key_in_response(client, settings):
    response, result = login(client)
    cookie = response.headers["set-cookie"].lower()
    for flag in ["httponly", "secure", "samesite=strict", "max-age=43200", "path=/api/admin"]:
        assert flag in cookie
    token = client.cookies.get(ADMIN_SESSION_COOKIE)
    assert len(token) == 43
    assert token not in response.text and KEY not in response.text and KEY not in cookie
    remaining = (datetime.fromisoformat(result["expiresAt"]) - datetime.now(timezone.utc)).total_seconds()
    assert 43_190 < remaining <= 43_200
    restored = client.get("/api/admin/session", headers={"Origin": ORIGIN})
    assert restored.status_code == 200 and restored.json() == result
    assert client.get("/api/admin/summary", headers={"Origin": ORIGIN}).status_code == 200
    with sqlite3.connect(settings.database_path) as connection:
        row = connection.execute("SELECT token_hash, csrf_token, key_fingerprint FROM admin_sessions").fetchone()
    assert row == (hashlib.sha256(token.encode()).hexdigest(), result["csrfToken"], key_fingerprint(KEY))
    assert token not in str(row) and KEY not in str(row)
    assert restored.headers["cache-control"] == "no-store"


def test_restoration_survives_application_restart_and_expiry_is_fixed(settings):
    with TestClient(create_app(settings), base_url="https://api.example.test") as first:
        _, original = login(first)
        token = first.cookies.get(ADMIN_SESSION_COOKIE)
    with TestClient(create_app(settings), base_url="https://api.example.test") as restarted:
        restored = restarted.get("/api/admin/session", headers={"Origin": ORIGIN, "Cookie": f"{ADMIN_SESSION_COOKIE}={token}"})
        assert restored.json() == original


def test_cookie_mutations_require_both_origin_and_csrf_and_logout_revokes(client):
    _, session = login(client)
    token = client.cookies.get(ADMIN_SESSION_COOKIE)
    endpoint = "/api/admin/invitations"
    body = {"familyName": "Familia", "seats": 3}
    assert client.post(endpoint, headers={"Origin": ORIGIN}, json=body).status_code == 403
    assert client.post(endpoint, headers={"X-CSRF-Token": session["csrfToken"], "Sec-Fetch-Site": "same-origin"}, json=body).status_code == 403
    assert client.post(endpoint, headers={"Origin": "https://evil.example", "X-CSRF-Token": session["csrfToken"]}, json=body).status_code == 403
    assert client.post(endpoint, headers={"Origin": ORIGIN, "X-CSRF-Token": "wrong"}, json=body).status_code == 403
    headers = {"Origin": ORIGIN, "X-CSRF-Token": session["csrfToken"]}
    assert client.post(endpoint, headers=headers, json=body).status_code == 201
    assert client.delete("/api/admin/session", headers={"Origin": ORIGIN}).status_code == 403
    logout = client.delete("/api/admin/session", headers=headers)
    assert logout.status_code == 200 and logout.json() == {"authenticated": False}
    assert "Max-Age=0" in logout.headers["set-cookie"]
    assert client.get("/api/admin/session", headers={"Origin": ORIGIN, "Cookie": f"{ADMIN_SESSION_COOKIE}={token}"}).status_code == 401


def test_transfer_configuration_rejects_public_and_cross_site_mutations(client):
    endpoint = '/api/admin/sections'
    sections = client.get(endpoint, headers=AUTH).json()
    updated = sections | {'bankTransfer': {'holder': 'Prueba', 'bank': 'Prueba', 'alias': 'alias.prueba', 'accountNumber': '', 'illustrative': False}}
    assert client.put(endpoint, json=updated).status_code == 401
    _, session = login(client)
    assert client.put(endpoint, headers={'Origin': ORIGIN}, json=updated).status_code == 403
    assert client.put(endpoint, headers={'Origin': 'https://evil.example', 'X-CSRF-Token': session['csrfToken']}, json=updated).status_code == 403
    assert client.get(endpoint, headers=AUTH).json() == sections
    response = client.put(endpoint, headers={'Origin': ORIGIN, 'X-CSRF-Token': session['csrfToken']}, json=updated)
    assert response.status_code == 200 and response.json() == updated


def test_get_without_origin_only_accepts_same_origin_fetch_metadata(client):
    login(client)
    assert client.get("/api/admin/session").status_code == 403
    assert client.get("/api/admin/session", headers={"Sec-Fetch-Site": "same-origin"}).status_code == 200
    assert client.get("/api/admin/session", headers={"Sec-Fetch-Site": "same-site"}).status_code == 403
    assert client.get("/api/admin/session", headers={"Origin": "null"}).status_code == 403
    assert client.get("/api/admin/session", headers=[("Origin", ORIGIN), ("Origin", ORIGIN)]).status_code == 403


def test_bootstrap_requires_original_key_not_cookie_or_csrf_or_opaque_token(client):
    _, session = login(client)
    token = client.cookies.get(ADMIN_SESSION_COOKIE)
    for headers in [{"Origin": ORIGIN}, {"Origin": ORIGIN, "X-CSRF-Token": session["csrfToken"]}, {"Origin": ORIGIN, "Authorization": f"Bearer {token}"}]:
        assert client.post("/api/admin/session", headers=headers).status_code == 401
    assert client.post("/api/admin/session", headers={"Authorization": f"Bearer {KEY}", "Origin": "https://evil.example"}).status_code == 403
    # Legacy CLI bootstrap, no browser Origin: stays supported, always Secure.
    response = client.post("/api/admin/session", headers={"Authorization": f"Bearer {KEY}"})
    assert response.status_code == 200 and "Secure" in response.headers["set-cookie"]


def test_new_login_replaces_current_cookie_session(client):
    login(client)
    original = client.cookies.get(ADMIN_SESSION_COOKIE)
    login(client)
    replacement = client.cookies.get(ADMIN_SESSION_COOKIE)
    assert replacement != original
    assert client.get("/api/admin/summary", headers={"Origin": ORIGIN, "Cookie": f"{ADMIN_SESSION_COOKIE}={original}"}).status_code == 401


def test_bad_authorization_never_falls_back_to_valid_cookie(client):
    login(client)
    assert client.get("/api/admin/summary", headers={"Origin": ORIGIN, "Authorization": "Bearer bad"}).status_code == 401
    assert client.get("/api/admin/summary", headers=[("Origin", ORIGIN), ("Authorization", f"Bearer {KEY}"), ("Authorization", f"Bearer {KEY}")]).status_code == 401


@pytest.mark.parametrize("token", ["bad", "A" * 43, "' OR 1=1--", "x" * 10_000])
def test_invalid_session_is_generic_401(client, token):
    response = client.get("/api/admin/session", headers={"Origin": ORIGIN, "Cookie": f"{ADMIN_SESSION_COOKIE}={token}"})
    assert response.status_code == 401 and response.json() == {"detail": "No autorizado"}


def test_duplicate_csrf_and_cookie_headers_rejected(client):
    _, session = login(client)
    token = client.cookies.get(ADMIN_SESSION_COOKIE)
    duplicate = f"{ADMIN_SESSION_COOKIE}={token}; {ADMIN_SESSION_COOKIE}={token}"
    assert client.get("/api/admin/session", headers={"Origin": ORIGIN, "Cookie": duplicate}).status_code == 401
    headers = [("Origin", ORIGIN), ("X-CSRF-Token", session["csrfToken"]), ("X-CSRF-Token", session["csrfToken"])]
    assert client.delete("/api/admin/session", headers=headers).status_code == 403


def test_expired_rotated_or_unconfigured_key_invalidates_session(settings):
    store = Database(settings.database_path)
    store.initialize()
    expired, _ = store.create_admin_session(key_fingerprint(KEY), now=1, lifetime=1)
    fresh, _ = store.create_admin_session(key_fingerprint(KEY))
    with TestClient(create_app(settings), base_url="https://api.example.test") as client:
        assert client.get("/api/admin/session", headers={"Origin": ORIGIN, "Cookie": f"{ADMIN_SESSION_COOKIE}={expired}"}).status_code == 401
    for key, expected in [("rotated-test-key-" + "y" * 32, 401), (None, 503)]:
        changed = Settings(database_path=settings.database_path, admin_api_key=key, allowed_origins=(ORIGIN,))
        with TestClient(create_app(changed), base_url="https://api.example.test") as client:
            assert client.get("/api/admin/session", headers={"Origin": ORIGIN, "Cookie": f"{ADMIN_SESSION_COOKIE}={fresh}"}).status_code == expected


@pytest.mark.parametrize("base,peer,origin,secure", [
    ("http://127.0.0.1:8000", "127.0.0.1", "http://127.0.0.1:5173", False),
    ("http://127.0.0.1:8000", "192.0.2.1", "http://127.0.0.1:5173", True),
    ("https://api.example.test", "127.0.0.1", ORIGIN, True),
    ("http://api.example.test", "127.0.0.1", ORIGIN, True),
])
def test_secure_cookie_exception_requires_local_host_peer_and_origin(settings, base, peer, origin, secure):
    with TestClient(create_app(settings), base_url=base, client=(peer, 50000)) as client:
        response = client.post("/api/admin/session", headers={"Authorization": f"Bearer {KEY}", "Origin": origin})
        assert response.status_code == 200
        assert ("Secure" in response.headers["set-cookie"]) is secure


def test_cors_credentials_csrf_delete_preflight_and_no_wildcard(client):
    response = client.options("/api/admin/session", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "DELETE", "Access-Control-Request-Headers": "X-CSRF-Token"})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"
    assert client.options("/api/admin/session", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "DELETE"}).status_code == 400


def test_root_path_cookie_is_scoped_to_prefixed_api(settings):
    with TestClient(create_app(settings), base_url="https://api.example.test/prefix", root_path="/prefix") as client:
        response = client.post("/api/admin/session", headers=AUTH)
        assert response.status_code == 200
        assert "Path=/prefix/api/admin" in response.headers["set-cookie"]
        session = client.get("/api/admin/session", headers={"Origin": ORIGIN})
        assert session.status_code == 200
        response = client.delete("/api/admin/session", headers={"Origin": ORIGIN, "X-CSRF-Token": session.json()["csrfToken"]})
        assert "Path=/prefix/api/admin" in response.headers["set-cookie"]


def test_bounded_sessions_and_pruning(settings):
    store = Database(settings.database_path)
    store.initialize()
    fingerprint = key_fingerprint(KEY)
    for stamp in range(100, 125):
        store.create_admin_session(fingerprint, now=stamp)
    with sqlite3.connect(settings.database_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM admin_sessions").fetchone()[0]
    assert count == 20
    store.create_admin_session(fingerprint, now=100_000)
    with sqlite3.connect(settings.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM admin_sessions").fetchone()[0] == 1


def test_adopts_existing_v2_database_without_overwriting_records(settings):
    store = Database(settings.database_path)
    store.initialize()
    with sqlite3.connect(settings.database_path) as connection:
        before = connection.execute("SELECT data_json FROM event").fetchone()[0]
        connection.execute("DROP TABLE admin_sessions")
        connection.execute("ALTER TABLE invitations DROP COLUMN token_ciphertext")
        connection.execute("DELETE FROM schema_migrations WHERE version >= 3")
    store.initialize()
    store.initialize()
    with sqlite3.connect(settings.database_path) as connection:
        assert connection.execute("SELECT data_json FROM event").fetchone()[0] == before
        assert connection.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall() == [(1,), (2,), (3,), (4,)]
