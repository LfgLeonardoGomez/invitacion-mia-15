"""Recoverable links retain public lookup hashes but never persist plaintext tokens."""

from dataclasses import replace
import hashlib
import json
import sqlite3
from uuid import uuid4

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
import pytest

from backend.app.config import Settings
from backend.app.database import Database
from backend.app.link_crypto import LinkCipher, LinkUnavailableError
from backend.app.main import create_app
from backend.app.models import InvitationCreate
from backend.tests.keys import TEST_LINK_KEY


ADMIN_KEY = "encrypted-link-test-administrator-" + "x" * 32
AUTH = {"Authorization": "Bearer " + ADMIN_KEY}
ORIGIN = "https://panel.example.test"


@pytest.fixture
def settings(tmp_path):
    return Settings(database_path=tmp_path / "private.sqlite3", admin_api_key=ADMIN_KEY,
                    allowed_origins=(ORIGIN,), link_encryption_key=TEST_LINK_KEY)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings), base_url="https://api.example.test") as current:
        yield current


def create(client, name="Familia cifrada"):
    response = client.post("/api/admin/invitations", headers=AUTH, json={"familyName": name, "seats": 3})
    assert response.status_code == 201
    return response.json()


def stored(settings, identifier):
    with sqlite3.connect(settings.database_path) as connection:
        return connection.execute("SELECT token_hash, token_ciphertext FROM invitations WHERE id = ?", (identifier,)).fetchone()


def test_new_link_is_encrypted_bound_and_admin_recoverable_after_restart(client, settings):
    invitation = create(client)
    digest, ciphertext = stored(settings, invitation["id"])
    assert digest == hashlib.sha256(invitation["token"].encode("ascii")).hexdigest()
    assert invitation["token"] not in ciphertext
    assert TEST_LINK_KEY not in ciphertext
    envelope = json.loads(Fernet(TEST_LINK_KEY).decrypt(ciphertext.encode("ascii")))
    assert envelope == {"id": invitation["id"], "token": invitation["token"]}
    url = f"/api/admin/invitations/{invitation['id']}/link"
    recovered = client.get(url, headers=AUTH)
    assert recovered.status_code == 200
    assert recovered.json() == {key: invitation[key] for key in ["id", "token", "invitationPath"]}
    assert recovered.headers["cache-control"] == "no-store"
    with TestClient(create_app(settings)) as reopened:
        assert reopened.get(url, headers=AUTH).json()["token"] == invitation["token"]
    with sqlite3.connect(settings.database_path) as connection:
        dump = "\n".join(connection.iterdump())
    assert invitation["token"] not in dump and TEST_LINK_KEY not in dump


def test_list_and_public_views_do_not_expose_ciphertexts_or_keys(client, settings):
    invitation = create(client)
    ciphertext = stored(settings, invitation["id"])[1]
    for response in [client.get("/api/admin/invitations", headers=AUTH),
                     client.get(f"/api/invitations/{invitation['token']}"),
                     client.get("/api/admin/summary", headers=AUTH)]:
        assert response.status_code == 200
        for secret in [ciphertext, TEST_LINK_KEY, invitation["token"], "tokenCiphertext", "token_ciphertext", "tokenHash"]:
            assert secret not in response.text


def test_recovery_requires_admin_cookie_or_bearer_and_origin(client):
    invitation = create(client)
    url = f"/api/admin/invitations/{invitation['id']}/link"
    assert client.get(url).status_code == 401
    assert client.get(url, headers={"Authorization": "Bearer " + "wrong" * 10}).status_code == 401
    login = client.post("/api/admin/session", headers=AUTH | {"Origin": ORIGIN})
    assert login.status_code == 200
    assert client.get(url, headers={"Origin": ORIGIN}).json()["token"] == invitation["token"]
    assert client.get(url, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get(f"/api/admin/invitations/{uuid4()}/link", headers=AUTH).status_code == 404


def test_rotation_replaces_cipher_and_hash_but_retains_responses(client, settings):
    invitation = create(client)
    public = f"/api/invitations/{invitation['token']}"
    response = client.put(public + "/rsvp", json={"attending": True, "guestCount": 2}).json()
    wish = client.post(public + "/wishes", json={"author": "Ana", "message": "Una hermosa noche", "clientRequestId": str(uuid4())}).json()
    original = stored(settings, invitation["id"])
    rotated = client.post(f"/api/admin/invitations/{invitation['id']}/rotate-token", headers=AUTH).json()
    assert stored(settings, invitation["id"])[0] != original[0]
    assert stored(settings, invitation["id"])[1] != original[1]
    assert client.get(public).status_code == 404
    current = client.get(f"/api/invitations/{rotated['token']}").json()
    assert current["rsvp"] == response and current["wish"] == wish
    assert client.get(f"/api/admin/invitations/{invitation['id']}/link", headers=AUTH).json() == rotated


def test_legacy_links_remain_valid_and_require_explicit_rotation(client, settings):
    invitation = create(client)
    with sqlite3.connect(settings.database_path) as connection:
        connection.execute("UPDATE invitations SET token_ciphertext = NULL WHERE id = ?", (invitation["id"],))
    original_hash = stored(settings, invitation["id"])[0]
    response = client.get(f"/api/admin/invitations/{invitation['id']}/link", headers=AUTH)
    assert response.status_code == 409
    assert "anterior" in response.json()["detail"]
    assert stored(settings, invitation["id"]) == (original_hash, None)
    assert client.get(f"/api/invitations/{invitation['token']}").status_code == 200
    rotated = client.post(f"/api/admin/invitations/{invitation['id']}/rotate-token", headers=AUTH).json()
    assert client.get(f"/api/admin/invitations/{invitation['id']}/link", headers=AUTH).json() == rotated


def test_missing_key_fails_closed_without_breaking_existing_links_or_other_features(client, settings):
    invitation = create(client)
    previous = stored(settings, invitation["id"])
    with TestClient(create_app(replace(settings, link_encryption_key=None))) as unconfigured:
        assert unconfigured.get("/api/health").status_code == 200
        assert unconfigured.get(f"/api/invitations/{invitation['token']}").status_code == 200
        assert unconfigured.put(f"/api/invitations/{invitation['token']}/rsvp", json={"attending": False, "guestCount": 0}).status_code == 200
        for method, path, body in [
            ("post", "/api/admin/invitations", {"familyName": "Not created", "seats": 1}),
            ("post", f"/api/admin/invitations/{invitation['id']}/rotate-token", None),
            ("get", f"/api/admin/invitations/{invitation['id']}/link", None),
        ]:
            response = getattr(unconfigured, method)(path, headers=AUTH, **({"json": body} if body is not None else {}))
            assert response.status_code == 503
            assert invitation["token"] not in response.text
        assert len(unconfigured.get("/api/admin/invitations", headers=AUTH).json()) == 1
    assert stored(settings, invitation["id"]) == previous


def test_wrong_key_does_not_expose_secret_or_break_guest_link(client, settings, caplog):
    invitation = create(client)
    wrong_key = Fernet.generate_key().decode("ascii")
    cipher = stored(settings, invitation["id"])[1]
    with TestClient(create_app(replace(settings, link_encryption_key=wrong_key))) as wrong:
        response = wrong.get(f"/api/admin/invitations/{invitation['id']}/link", headers=AUTH)
        assert response.status_code == 503
        assert wrong.get(f"/api/invitations/{invitation['token']}").status_code == 200
    for secret in [invitation["token"], TEST_LINK_KEY, wrong_key, cipher]:
        assert secret not in response.text and secret not in caplog.text


@pytest.mark.parametrize("tamper", ["malformed", "cipher_swap", "hash_swap", "both_swap", "wrong_envelope"])
def test_corruption_or_cross_family_substitution_is_rejected(client, settings, tamper):
    first, second = create(client), create(client, "Otra familia")
    first_hash, first_cipher = stored(settings, first["id"])
    second_hash, second_cipher = stored(settings, second["id"])
    digest, ciphertext = {
        "malformed": (first_hash, "not-a-ciphertext"),
        "cipher_swap": (first_hash, second_cipher),
        "hash_swap": (second_hash, first_cipher),
        "both_swap": (second_hash, second_cipher),
        "wrong_envelope": (first_hash, Fernet(TEST_LINK_KEY).encrypt(json.dumps({"id": first["id"], "token": "invalid"}).encode()).decode()),
    }[tamper]
    with sqlite3.connect(settings.database_path) as connection:
        if tamper in {"hash_swap", "both_swap"}:
            connection.execute("UPDATE invitations SET token_hash = ? WHERE id = ?", ("0" * 64, second["id"]))
        connection.execute("UPDATE invitations SET token_hash = ?, token_ciphertext = ? WHERE id = ?", (digest, ciphertext, first["id"]))
    response = client.get(f"/api/admin/invitations/{first['id']}/link", headers=AUTH)
    assert response.status_code == 503
    assert first["token"] not in response.text and second["token"] not in response.text


def test_encryption_failure_is_atomic_and_does_not_revoke_old_link(client, settings, monkeypatch):
    invitation = create(client)
    old = stored(settings, invitation["id"])
    def fail(*args):
        raise LinkUnavailableError
    monkeypatch.setattr(client.app.state.database.link_cipher, "encrypt", fail)
    assert client.post(f"/api/admin/invitations/{invitation['id']}/rotate-token", headers=AUTH).status_code == 503
    assert client.post("/api/admin/invitations", headers=AUTH, json={"familyName": "Not created", "seats": 1}).status_code == 503
    assert stored(settings, invitation["id"]) == old
    assert len(client.get("/api/admin/invitations", headers=AUTH).json()) == 1
    assert client.get(f"/api/invitations/{invitation['token']}").status_code == 200


def test_sql_failure_rolls_back_hash_and_cipher_together(client, settings):
    invitation = create(client)
    previous = stored(settings, invitation["id"])
    with sqlite3.connect(settings.database_path) as connection:
        connection.execute("CREATE TRIGGER reject_rotation BEFORE UPDATE OF token_hash ON invitations BEGIN SELECT RAISE(ABORT, 'fixture write rejected'); END")
    with pytest.raises(sqlite3.IntegrityError):
        client.app.state.database.rotate_token(invitation["id"])
    assert stored(settings, invitation["id"]) == previous
    assert client.get(f"/api/admin/invitations/{invitation['id']}/link", headers=AUTH).json()["token"] == invitation["token"]


def test_migration_from_v3_does_not_replace_legacy_tokens_or_answers(client, settings):
    invitation = create(client)
    answer = client.put(f"/api/invitations/{invitation['token']}/rsvp", json={"attending": True, "guestCount": 2}).json()
    with sqlite3.connect(settings.database_path) as connection:
        connection.execute("ALTER TABLE invitations DROP COLUMN token_ciphertext")
        connection.execute("DELETE FROM schema_migrations WHERE version = 4")
    with TestClient(create_app(settings)) as reopened:
        actual = reopened.get(f"/api/invitations/{invitation['token']}")
        assert actual.status_code == 200 and actual.json()["rsvp"] == answer
        assert reopened.get(f"/api/admin/invitations/{invitation['id']}/link", headers=AUTH).status_code == 409
    assert stored(settings, invitation["id"]) == (hashlib.sha256(invitation["token"].encode()).hexdigest(), None)


@pytest.mark.parametrize("key", ["", "weak", " " + TEST_LINK_KEY, TEST_LINK_KEY + "\n", "!" * 43 + "=", "A" * 44])
def test_invalid_encryption_keys_fail_settings_validation(key):
    with pytest.raises(ValueError, match="MIA_LINK_ENCRYPTION_KEY"):
        Settings(link_encryption_key=key)


def test_key_cannot_be_reused_as_admin_key_or_included_in_settings_repr(monkeypatch):
    with pytest.raises(ValueError, match="distinct"):
        Settings(admin_api_key=TEST_LINK_KEY, link_encryption_key=TEST_LINK_KEY)
    monkeypatch.setenv("MIA_LINK_ENCRYPTION_KEY", TEST_LINK_KEY)
    settings = Settings.from_environment()
    assert settings.link_encryption_key == TEST_LINK_KEY
    assert TEST_LINK_KEY not in repr(settings)
