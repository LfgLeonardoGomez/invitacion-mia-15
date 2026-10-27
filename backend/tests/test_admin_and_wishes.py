"""Integration coverage for additive sections, private wishes and organizer views."""

from concurrent.futures import ThreadPoolExecutor
import sqlite3
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from backend.app.config import Settings
from backend.app.database import Database, WishLimitError
from backend.app.main import create_app
from backend.app.models import DEFAULT_SECTIONS, WishInput
from backend.tests.keys import TEST_LINK_KEY


KEY = "test-only-organizer-key-" + "x" * 32
AUTH = {"Authorization": f"Bearer {KEY}"}


@pytest.fixture
def settings(tmp_path):
    return Settings(database_path=tmp_path / "private" / "v2.sqlite3", admin_api_key=KEY, link_encryption_key=TEST_LINK_KEY)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as current:
        yield current


def family(client, name="Familia Pérez", seats=3):
    response = client.post("/api/admin/invitations", headers=AUTH, json={"familyName": name, "seats": seats})
    assert response.status_code == 201, response.text
    return response.json()


def wish(author="Ana", message="¡Feliz cumple!", request_id=None):
    return {"author": author, "message": message, "clientRequestId": request_id or str(uuid4())}


def test_sections_default_replace_and_private_wishes_persist(settings):
    with TestClient(create_app(settings)) as first:
        invite = family(first)
        public_url = f"/api/invitations/{invite['token']}"
        payload = first.get(public_url).json()
        assert payload["sections"] == DEFAULT_SECTIONS.model_dump(by_alias=True)
        assert payload["wish"] is None
        assert payload["event"]["dressCode"] == "Elegante Sport"
        sections = payload["sections"] | {"bankTransfer": None, "contact": {"whatsappNumber": ""}}
        assert first.put("/api/admin/sections", headers=AUTH, json=sections).json() == sections
        response = first.post(public_url + "/wishes", json=wish("  Ana  ", "  Un abrazo  "))
        assert response.status_code == 201, response.text
        saved = response.json()
        assert saved["author"] == "Ana" and saved["message"] == "Un abrazo"
        assert set(saved) == {"id", "author", "message", "createdAt", "updatedAt"}
        assert saved["updatedAt"] == saved["createdAt"]
    with TestClient(create_app(settings)) as second:
        payload = second.get(public_url).json()
        assert payload["sections"] == sections
        assert payload["wish"] == saved
        assert second.get("/api/admin/sections", headers=AUTH).json() == sections
        listed = second.get("/api/admin/wishes", headers=AUTH).json()
        assert listed == [saved | {"invitationId": invite["id"], "familyName": invite["familyName"]}]


def test_wishes_are_private_append_only_and_idempotent(client):
    one = family(client, "Familia Uno")
    two = family(client, "Familia Dos")
    url = f"/api/invitations/{one['token']}/wishes"
    body = wish(message="<img src=x onerror=alert(1)>")
    first = client.post(url, json=body)
    assert first.status_code == 201
    assert client.post(url, json=body).json() == first.json()
    assert client.post(url, json=body | {"message": "changed"}).status_code == 409
    last = client.post(url, json=wish("Pedro", "Otro deseo")).json()
    assert client.get(url.removesuffix("/wishes")).json()["wish"] == last
    public_two = client.get(f"/api/invitations/{two['token']}")
    assert public_two.json()["wish"] is None
    assert one["id"] not in public_two.text and "Familia Uno" not in public_two.text
    # A request key is scoped to the invitation, not a global correlation identifier.
    assert client.post(f"/api/invitations/{two['token']}/wishes", json=body).status_code == 201
    listed = client.get("/api/admin/wishes", headers=AUTH).json()
    assert len(listed) == 3
    assert listed[1]["message"] == "Otro deseo"
    assert "clientRequestId" not in listed[0] and "token" not in str(listed)


@pytest.mark.parametrize("changes", [
    {"author": " "}, {"author": "a" * 81}, {"message": " "}, {"message": "m" * 601},
    {"author": 9}, {"message": False}, {"clientRequestId": "not-a-uuid"},
    {"clientRequestId": None}, {"invitationId": "injected"},
    {"author": "\u0000"}, {"message": "\u0000invisible"},
])
def test_wish_input_is_strict_and_bounded(client, changes):
    invite = family(client)
    url = f"/api/invitations/{invite['token']}"
    assert client.post(url + "/wishes", json=wish() | changes).status_code == 422
    assert client.get(url).json()["wish"] is None


def test_wishes_reject_unknown_revoked_and_rotated_tokens(client):
    invite = family(client)
    url = f"/api/invitations/{invite['token']}/wishes"
    assert client.post("/api/invitations/invalid/wishes", json=wish()).status_code == 404
    patch = f"/api/admin/invitations/{invite['id']}"
    client.patch(patch, headers=AUTH, json={"active": False})
    assert client.post(url, json=wish()).status_code == 404
    client.patch(patch, headers=AUTH, json={"active": True})
    rotated = client.post(patch + "/rotate-token", headers=AUTH).json()
    assert client.post(url, json=wish()).status_code == 404
    assert client.post(f"/api/invitations/{rotated['token']}/wishes", json=wish()).status_code == 201


def test_wish_limit_and_parallel_idempotency(client, settings):
    invite = family(client)
    store = Database(settings.database_path)
    body = WishInput(**wish())
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: store.save_wish(invite["token"], body), range(4)))
    assert len({result.id for result in results}) == 1
    for _ in range(8):
        store.save_wish(invite["token"], WishInput(**wish()))
    with ThreadPoolExecutor(max_workers=2) as pool:
        def try_create(_):
            try:
                return store.save_wish(invite["token"], WishInput(**wish())).id
            except WishLimitError:
                return None
        results = list(pool.map(try_create, range(2)))
    assert sum(result is not None for result in results) == 1
    assert store.save_wish(invite["token"], body).id == body_id(store, invite["id"], body.client_request_id)
    limited = client.post(f"/api/invitations/{invite['token']}/wishes", json=wish())
    assert limited.status_code == 409
    assert limited.json()['code'] == 'wish_limit_reached'
    assert limited.json()['maxWishes'] == 10
    assert store.summary().total_wishes == 10


def test_lowered_wish_limit_preserves_historical_messages_and_idempotent_retries(client, settings):
    invite = family(client)
    store = Database(settings.database_path)
    original = WishInput(**wish())
    first = store.save_wish(invite['token'], original)
    # Simulate records accepted under the former larger cap; never prune them.
    with store.transaction(write=True) as connection:
        for _ in range(11):
            connection.execute('INSERT INTO wishes VALUES (?, ?, ?, ?, ?, ?)',
                               (str(uuid4()), invite['id'], str(uuid4()), 'Ana', 'Deseo anterior', '2026-10-26T00:00:00Z'))
    assert store.save_wish(invite['token'], original).id == first.id
    with pytest.raises(WishLimitError):
        store.save_wish(invite['token'], WishInput(**wish()))
    assert store.summary().total_wishes == 12
    assert len(store.list_wishes(limit=50, offset=0)) == 12


def body_id(store, invitation_id, request_id):
    with store.transaction() as connection:
        return connection.execute("SELECT id FROM wishes WHERE invitation_id = ? AND client_request_id = ?", (invitation_id, request_id)).fetchone()[0]


def test_summary_and_status_filters_distinguish_families_and_people(client):
    confirmed = family(client, "Confirmada", 4)
    declined = family(client, "Rechazada", 2)
    pending = family(client, "Pendiente", 3)
    inactive = family(client, "Inactiva", 6)
    for invite, count in [(confirmed, 2), (inactive, 5)]:
        client.put(f"/api/invitations/{invite['token']}/rsvp", json={"attending": True, "guestCount": count})
    client.put(f"/api/invitations/{declined['token']}/rsvp", json={"attending": False, "guestCount": 0})
    client.post(f"/api/invitations/{inactive['token']}/wishes", json=wish())
    client.patch(f"/api/admin/invitations/{inactive['id']}", headers=AUTH, json={"active": False})
    summary = client.get("/api/admin/summary", headers=AUTH).json()
    assert summary == {"totalInvitations": 4, "activeInvitations": 3, "confirmedInvitations": 1, "declinedInvitations": 1, "pendingInvitations": 1, "confirmedGuests": 2, "reservedSeats": 9, "totalWishes": 1}
    for status, expected in [("confirmed", confirmed), ("declined", declined), ("pending", pending)]:
        rows = client.get(f"/api/admin/invitations?status={status}", headers=AUTH).json()
        assert [row["id"] for row in rows] == [expected["id"]]
    assert len(client.get("/api/admin/invitations", headers=AUTH).json()) == 4
    active_rows = client.get('/api/admin/invitations?status=active', headers=AUTH).json()
    assert {row['id'] for row in active_rows} == {confirmed['id'], declined['id'], pending['id']}
    inactive_rows = client.get('/api/admin/invitations?status=inactive', headers=AUTH).json()
    assert [row['id'] for row in inactive_rows] == [inactive['id']]
    assert inactive_rows[0]['rsvp']['guestCount'] == 5
    assert len(client.get('/api/admin/invitations?status=active&limit=1&offset=1', headers=AUTH).json()) == 1
    assert client.get('/api/admin/invitations?status=inactive&q=Confirmada', headers=AUTH).json() == []
    client.patch(f"/api/admin/invitations/{inactive['id']}", headers=AUTH, json={'active': True})
    assert client.get('/api/admin/invitations?status=inactive', headers=AUTH).json() == []
    assert len(client.get('/api/admin/invitations?status=active', headers=AUTH).json()) == 4
    assert client.get(f"/api/invitations/{inactive['token']}").json()['rsvp']['guestCount'] == 5
    assert client.get("/api/admin/invitations?status=unknown", headers=AUTH).status_code == 422


def test_literal_search_and_pagination(client):
    one = family(client, "Familia 100%_\\")
    family(client, "Familia normal")
    for message in ["100%_\\", "cualquier cosa"]:
        assert client.post(f"/api/invitations/{one['token']}/wishes", json=wish(message=message)).status_code == 201
    result = client.get("/api/admin/invitations", headers=AUTH, params={"q": "%_\\"}).json()
    assert [row["id"] for row in result] == [one["id"]]
    assert len(client.get("/api/admin/wishes", headers=AUTH, params={"q": "100%_\\"}).json()) == 2  # family name also matches
    assert len(client.get("/api/admin/wishes", headers=AUTH, params={"q": "cualquier"}).json()) == 1
    assert client.get("/api/admin/wishes", headers=AUTH, params={"q": "' OR 1=1--"}).json() == []
    assert len(client.get("/api/admin/wishes?limit=1&offset=1", headers=AUTH).json()) == 1
    for path in ["/api/admin/wishes?limit=201", "/api/admin/wishes?offset=-1", "/api/admin/invitations?q=" + "a" * 121]:
        assert client.get(path, headers=AUTH).status_code == 422


@pytest.mark.parametrize("method,path", [
    ("get", "/api/admin/sections"), ("put", "/api/admin/sections"),
    ("get", "/api/admin/summary"), ("get", "/api/admin/wishes"),
])
def test_new_admin_routes_require_key(client, method, path):
    options = {"json": DEFAULT_SECTIONS.model_dump(by_alias=True)} if method == "put" else {}
    assert getattr(client, method)(path, **options).status_code == 401


@pytest.mark.parametrize("changes", [
    {"eventUtcOffset": "+99:99"}, {"contact": {"whatsappNumber": "+54 911"}},
    {"contact": {"whatsappNumber": "javascript:alert(1)"}}, {"extra": "no"},
    {"bankTransfer": {"holder": "x", "bank": "x", "alias": "", "accountNumber": "", "illustrative": False}},
    {"bankTransfer": {"holder": "x", "bank": "x", "accountNumber": "123", "illustrative": "true"}},
])
def test_invalid_sections_are_rejected_without_mutation(client, changes):
    original = DEFAULT_SECTIONS.model_dump(by_alias=True)
    assert client.put("/api/admin/sections", headers=AUTH, json=original | changes).status_code == 422
    assert client.get("/api/admin/sections", headers=AUTH).json() == original


def test_legacy_database_migration_preserves_event_family_rsvp_and_runs_once(settings):
    with TestClient(create_app(settings)) as client:
        invite = family(client)
        event = client.get("/api/admin/event", headers=AUTH).json() | {"dressCode": "Custom dress"}
        client.put("/api/admin/event", headers=AUTH, json=event)
        response = client.put(f"/api/invitations/{invite['token']}/rsvp", json={"attending": True, "guestCount": 3}).json()
    # Exact original three-table database state, no version metadata or v2 objects.
    with sqlite3.connect(settings.database_path) as connection:
        for table in ["admin_sessions", "wishes", "event_sections", "schema_migrations"]:
            connection.execute("DROP TABLE " + table)
        connection.execute("ALTER TABLE invitations DROP COLUMN token_ciphertext")
    for _ in range(2):
        with TestClient(create_app(settings)) as client:
            payload = client.get(f"/api/invitations/{invite['token']}").json()
            assert payload["event"] == event
            assert payload["rsvp"] == response
            assert payload["sections"] == DEFAULT_SECTIONS.model_dump(by_alias=True)
    with sqlite3.connect(settings.database_path) as connection:
        assert connection.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall() == [(1,), (2,), (3,), (4,)]


def test_unknown_future_schema_fails_closed(settings):
    store = Database(settings.database_path)
    store.initialize()
    with sqlite3.connect(settings.database_path) as connection:
        connection.execute("INSERT INTO schema_migrations VALUES (999, 'future')")
    with pytest.raises(RuntimeError, match="newer"):
        store.initialize()


def test_wish_rate_limit_does_not_block_rsvp_or_read(client):
    invite = family(client)
    url = f"/api/invitations/{invite['token']}"
    for _ in range(10):
        assert client.post(url + "/wishes", json=wish()).status_code == 201
    response = client.post(url + "/wishes", json=wish())
    assert response.status_code == 429
    assert response.headers["retry-after"]
    assert response.headers["cache-control"] == "no-store"
    assert client.put(url + "/rsvp", json={"attending": True, "guestCount": 1}).status_code == 200
    assert client.get(url).status_code == 200
