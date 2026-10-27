from concurrent.futures import ThreadPoolExecutor
import hashlib
import sqlite3
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import DEFAULT_EVENT
from backend.tests.keys import TEST_LINK_KEY


ADMIN_KEY = "test-only-secret-not-for-deployment-0123456789"
AUTH = {"Authorization": f"Bearer {ADMIN_KEY}"}


@pytest.fixture
def settings(tmp_path):
    return Settings(database_path=tmp_path / "private" / "invitations.sqlite3", admin_api_key=ADMIN_KEY, link_encryption_key=TEST_LINK_KEY)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as current:
        yield current


def create_family(client, name="Familia de prueba", seats=4):
    response = client.post("/api/admin/invitations", headers=AUTH, json={"familyName": name, "seats": seats})
    assert response.status_code == 201, response.text
    return response.json()


def test_health_no_demo_families_or_public_docs(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/admin/invitations", headers=AUTH).json() == []
    assert client.get("/api/docs").status_code == 404
    assert client.get("/api/openapi.json").status_code == 404
    assert client.get("/assets/../data/invitations.sqlite3").status_code == 404


def test_public_contract_and_token_never_persisted_in_clear(client, settings):
    family = create_family(client, "  Familia uno  ")
    assert family["familyName"] == "Familia uno"
    assert len(family["token"]) == 43
    assert family["invitationPath"] == f"/?invitation={family['token']}"
    public = client.get(f"/api/invitations/{family['token']}")
    assert public.status_code == 200
    data = public.json()
    assert set(data) == {"event", "invitation", "rsvp", "sections", "wish"}
    assert data["event"] == DEFAULT_EVENT.model_dump(by_alias=True)
    assert data["invitation"] == {"id": family["id"], "familyName": "Familia uno", "seats": 4}
    assert data["rsvp"] is None
    assert "token" not in public.text and "hash" not in public.text
    with sqlite3.connect(settings.database_path) as connection:
        stored = connection.execute("SELECT token_hash FROM invitations").fetchone()[0]
    assert stored == hashlib.sha256(family["token"].encode("ascii")).hexdigest()
    listed = client.get("/api/admin/invitations", headers=AUTH).json()
    assert "token" not in listed[0] and "tokenHash" not in listed[0]


@pytest.mark.parametrize("token", ["invalid", "A" * 43, "' OR 1=1--", "á" * 43])
def test_unknown_or_malformed_tokens_are_generic_404(client, token):
    response = client.get(f"/api/invitations/{token}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Invitación no encontrada."}


def test_rsvp_is_idempotent_editable_and_visible_to_admin(client):
    family = create_family(client)
    url = f"/api/invitations/{family['token']}/rsvp"
    first = client.put(url, json={"attending": True, "guestCount": 3})
    assert first.status_code == 200
    assert first.json()["guestCount"] == 3
    assert set(first.json()) == {"attending", "guestCount", "updatedAt"}
    second = client.put(url, json={"attending": True, "guestCount": 3})
    assert second.json() == first.json(), "Identical PUT should not rewrite its timestamp"
    declined = client.put(url, json={"attending": False, "guestCount": 0})
    assert declined.status_code == 200
    assert declined.json()["attending"] is False
    public = client.get(f"/api/invitations/{family['token']}").json()
    assert public["rsvp"] == declined.json()
    admin = client.get("/api/admin/invitations", headers=AUTH).json()
    assert admin[0]["rsvp"] == declined.json()


@pytest.mark.parametrize("answer", [
    {"attending": True, "guestCount": 5},
    {"attending": True, "guestCount": 0},
    {"attending": False, "guestCount": 1},
    {"attending": "true", "guestCount": 2},
    {"attending": 1, "guestCount": 2},
    {"attending": True, "guestCount": "2"},
    {"attending": True, "guestCount": True},
    {"attending": True, "guestCount": 2.5},
    {"attending": True, "guestCount": -1},
    {"attending": True, "guestCount": 51},
    {"attending": True, "guestCount": 2, "seats": 999},
    {"attending": True, "guestCount": 2, "invitationId": "another-family"},
    {"attending": None, "guestCount": 0},
])
def test_rsvp_rejects_overquota_coercion_and_unknown_fields(client, answer):
    family = create_family(client)
    response = client.put(f"/api/invitations/{family['token']}/rsvp", json=answer)
    assert response.status_code == 422, response.text
    assert client.get(f"/api/invitations/{family['token']}").json()["rsvp"] is None


def test_family_isolation(client):
    one = create_family(client, "Familia uno", 2)
    two = create_family(client, "Familia dos", 6)
    client.put(f"/api/invitations/{one['token']}/rsvp", json={"attending": True, "guestCount": 2})
    public_two = client.get(f"/api/invitations/{two['token']}")
    assert public_two.json()["rsvp"] is None
    assert "Familia uno" not in public_two.text
    assert one["id"] not in public_two.text
    assert client.put(f"/api/invitations/{one['token']}/rsvp", json={"attending": True, "guestCount": 6}).status_code == 422


def test_revocation_reactivation_rotation_and_preserved_response(client):
    family = create_family(client)
    token = family["token"]
    response = client.put(f"/api/invitations/{token}/rsvp", json={"attending": True, "guestCount": 2}).json()
    patch_url = f"/api/admin/invitations/{family['id']}"
    assert client.patch(patch_url, headers=AUTH, json={"active": False}).status_code == 200
    assert client.get(f"/api/invitations/{token}").status_code == 404
    assert client.put(f"/api/invitations/{token}/rsvp", json={"attending": False, "guestCount": 0}).status_code == 404
    assert client.patch(patch_url, headers=AUTH, json={"active": True}).status_code == 200
    rotated = client.post(f"{patch_url}/rotate-token", headers=AUTH)
    assert rotated.status_code == 200, rotated.text
    new_token = rotated.json()["token"]
    assert new_token != token
    assert client.get(f"/api/invitations/{token}").status_code == 404
    assert client.get(f"/api/invitations/{new_token}").json()["rsvp"] == response


def test_admin_cannot_reduce_quota_below_existing_confirmation(client):
    family = create_family(client)
    client.put(f"/api/invitations/{family['token']}/rsvp", json={"attending": True, "guestCount": 4})
    patch = f"/api/admin/invitations/{family['id']}"
    assert client.patch(patch, headers=AUTH, json={"seats": 2}).status_code == 409
    assert client.get(f"/api/invitations/{family['token']}").json()["invitation"]["seats"] == 4
    assert client.patch(patch, headers=AUTH, json={"seats": 5}).json()["seats"] == 5


def test_parallel_quota_edit_and_response_cannot_violate_quota(client):
    family = create_family(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        rsvp = pool.submit(client.put, f"/api/invitations/{family['token']}/rsvp", json={"attending": True, "guestCount": 4})
        quota = pool.submit(client.patch, f"/api/admin/invitations/{family['id']}", headers=AUTH, json={"seats": 2})
        statuses = {rsvp.result().status_code, quota.result().status_code}
    assert statuses in ({200, 409}, {200, 422})
    state = client.get(f"/api/invitations/{family['token']}").json()
    assert state["rsvp"] is None or state["rsvp"]["guestCount"] <= state["invitation"]["seats"]


@pytest.mark.parametrize("patch", [{}, {"seats": None}, {"familyName": " "}, {"active": "false"}, {"seats": True}, {"tokenHash": "overwrite"}])
def test_invalid_admin_patch_is_rejected(client, patch):
    family = create_family(client)
    response = client.patch(f"/api/admin/invitations/{family['id']}", headers=AUTH, json=patch)
    assert response.status_code == 422


@pytest.mark.parametrize("payload", [{"familyName": "", "seats": 4}, {"familyName": "x", "seats": 0}, {"familyName": "x", "seats": 51}, {"familyName": "x", "seats": "4"}, {"familyName": "x", "seats": True}, {"familyName": "x", "seats": 4, "token": "public-demo"}])
def test_invalid_family_is_rejected(client, payload):
    assert client.post("/api/admin/invitations", headers=AUTH, json=payload).status_code == 422


def test_event_update_persists_and_is_returned_to_guest(client):
    family = create_family(client)
    event = DEFAULT_EVENT.model_dump(by_alias=True)
    event["venueName"] = "Salón actualizado"
    event["arrivalTime"] = "20:00"
    assert client.put("/api/admin/event", headers=AUTH, json=event).json() == event
    assert client.get(f"/api/invitations/{family['token']}").json()["event"] == event


@pytest.mark.parametrize("changes", [{"date": "2026-02-30"}, {"arrivalTime": "29:50"}, {"entranceTime": "18:00"}, {"bankAlias": "not-approved"}, {"name": " "}])
def test_invalid_event_update_is_rejected(client, changes):
    event = DEFAULT_EVENT.model_dump(by_alias=True) | changes
    assert client.put("/api/admin/event", headers=AUTH, json=event).status_code == 422


def test_persistence_across_app_restarts(settings):
    with TestClient(create_app(settings)) as first:
        family = create_family(first)
        answer = first.put(f"/api/invitations/{family['token']}/rsvp", json={"attending": True, "guestCount": 4}).json()
        event = DEFAULT_EVENT.model_dump(by_alias=True) | {"name": "Mia actualizado"}
        first.put("/api/admin/event", headers=AUTH, json=event)
    with TestClient(create_app(settings)) as second:
        actual = second.get(f"/api/invitations/{family['token']}").json()
        assert actual["event"]["name"] == "Mia actualizado"
        assert actual["rsvp"] == answer


def test_admin_routes_fail_closed_without_key(tmp_path):
    with TestClient(create_app(Settings(database_path=tmp_path / "disabled.sqlite3"))) as client:
        assert client.get("/api/admin/invitations").status_code == 503
        assert client.post("/api/admin/invitations", json={"familyName": "x", "seats": 1}).status_code == 503


@pytest.mark.parametrize("method,path,payload", [
    ("get", "/api/admin/event", None),
    ("put", "/api/admin/event", DEFAULT_EVENT.model_dump(by_alias=True)),
    ("get", "/api/admin/invitations", None),
    ("post", "/api/admin/invitations", {"familyName": "x", "seats": 1}),
    ("patch", f"/api/admin/invitations/{uuid4()}", {"active": False}),
    ("post", f"/api/admin/invitations/{uuid4()}/rotate-token", None),
])
def test_all_admin_operations_require_authorization(client, method, path, payload):
    response = getattr(client, method)(path, **({"json": payload} if payload is not None else {}))
    assert response.status_code == 401


def test_unknown_ids_and_pagination_are_bounded(client):
    identifier = str(uuid4())
    assert client.patch(f"/api/admin/invitations/{identifier}", headers=AUTH, json={"active": False}).status_code == 404
    assert client.post(f"/api/admin/invitations/{identifier}/rotate-token", headers=AUTH).status_code == 404
    assert client.get("/api/admin/invitations?limit=201", headers=AUTH).status_code == 422
    assert client.get("/api/admin/invitations?offset=-1", headers=AUTH).status_code == 422


def test_settings_reject_weak_secret_and_unsafe_origins(tmp_path):
    with pytest.raises(ValueError):
        Settings(database_path=tmp_path / "x", admin_api_key="weak")
    for origin in ["*", "null", "https://*.example.com", "https://example.com/path", "https://user:password@example.com", "javascript:bad"]:
        with pytest.raises(ValueError):
            Settings(allowed_origins=(origin,))


def test_empty_environment_database_path_uses_private_default(monkeypatch):
    from backend.app.config import DEFAULT_DATABASE_PATH

    monkeypatch.setenv("MIA_DATABASE_PATH", "")
    monkeypatch.setenv("MIA_ADMIN_API_KEY", "")
    monkeypatch.setenv("MIA_ALLOWED_ORIGINS", "")
    monkeypatch.setenv("MIA_ENABLE_DOCS", "false")
    settings = Settings.from_environment()
    assert settings.database_path == DEFAULT_DATABASE_PATH
    assert settings.admin_api_key is None


def test_native_telemetry_is_explicitly_disabled(settings, monkeypatch):
    monkeypatch.setenv("FASTAPI_OTEL_AUTO_CONFIGURE", "true")
    app = create_app(settings)
    # Older globally installed FastAPI has no native telemetry support.
    if hasattr(app, "_telemetry"):
        for signal in ("tracing", "metrics", "logs", "operation_spans", "auto_configure"):
            assert app._telemetry[signal] is False


def test_explicit_cors_and_credentials_for_private_sessions(tmp_path):
    settings = Settings(database_path=tmp_path / "cors.sqlite3", admin_api_key=ADMIN_KEY, allowed_origins=("https://invite.example",))
    with TestClient(create_app(settings)) as client:
        allowed = client.get("/api/health", headers={"Origin": "https://invite.example"})
        assert allowed.headers["access-control-allow-origin"] == "https://invite.example"
        assert allowed.headers["access-control-allow-credentials"] == "true"
        blocked = client.get("/api/health", headers={"Origin": "https://evil.example"})
        assert "access-control-allow-origin" not in blocked.headers
