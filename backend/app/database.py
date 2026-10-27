"""Small transactional SQLite store for one event.

Connections are opened/closed per operation. No database connection is shared
between FastAPI worker threads, and public tokens are never persisted in clear.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from typing import Iterator
from uuid import uuid4

from .link_crypto import LegacyLinkError, LinkCipher

from .models import (
    AdminInvitation,
    AdminSummary,
    AdminWish,
    CreatedInvitation,
    DEFAULT_EVENT,
    DEFAULT_SECTIONS,
    EventData,
    InvitationCreate,
    InvitationData,
    InvitationPatch,
    InvitationResponse,
    RotatedToken,
    RsvpData,
    RsvpInput,
    SectionsData,
    WishData,
    WishInput,
)


MAX_WISHES_PER_INVITATION = 10


class NotFoundError(Exception):
    """A nonexistent, invalid, or inactive invitation."""


class QuotaExceededError(Exception):
    """The requested response exceeds the invitation's authoritative quota."""


class ConfirmationConflictError(Exception):
    """An administrative change would invalidate an existing response."""


class WishConflictError(Exception):
    """A wish request key has already been used for different contents."""


class WishLimitError(Exception):
    """An invitation has reached its bounded message allowance."""


def literal_search(value: str) -> str:
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def wish_from_row(row: sqlite3.Row) -> WishData:
    return WishData(id=row["id"], author=row["author"], message=row["message"],
                    created_at=row["created_at"], updated_at=row["created_at"])


JOIN_INVITATIONS = """
SELECT i.id, i.family_name, i.seats, i.active, i.created_at, i.updated_at,
       r.attending AS rsvp_attending, r.guest_count AS rsvp_guest_count,
       r.updated_at AS rsvp_updated_at
FROM invitations AS i
LEFT JOIN rsvps AS r ON r.invitation_id = i.id
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def token_lookup_hash(token: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_-]{43}", token) is None:
        raise NotFoundError
    return token_hash(token)


def rsvp_from_row(row: sqlite3.Row) -> RsvpData | None:
    if row["rsvp_attending"] is None:
        return None
    return RsvpData(
        attending=bool(row["rsvp_attending"]),
        guest_count=row["rsvp_guest_count"],
        updated_at=row["rsvp_updated_at"],
    )


def admin_from_row(row: sqlite3.Row) -> AdminInvitation:
    return AdminInvitation(
        id=row["id"],
        family_name=row["family_name"],
        seats=row["seats"],
        active=bool(row["active"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        rsvp=rsvp_from_row(row),
    )


class Database:
    def __init__(self, path: Path, link_encryption_key: str | None = None) -> None:
        self.path = path
        self.link_cipher = LinkCipher(link_encryption_key)

    @contextmanager
    def transaction(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(str(self.path), timeout=5, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        connection = sqlite3.connect(str(self.path), timeout=5, isolation_level=None)
        try:
            connection.execute("PRAGMA journal_mode = WAL")
        finally:
            connection.close()
        if os.name != "nt":
            os.chmod(self.path, 0o600)
        with self.transaction(write=True) as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS event (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    data_json TEXT NOT NULL
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS invitations (
                    id TEXT PRIMARY KEY,
                    family_name TEXT NOT NULL CHECK (length(family_name) BETWEEN 1 AND 120),
                    seats INTEGER NOT NULL CHECK (seats BETWEEN 1 AND 50),
                    token_hash TEXT NOT NULL UNIQUE CHECK (length(token_hash) = 64),
                    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS rsvps (
                    invitation_id TEXT PRIMARY KEY REFERENCES invitations(id) ON DELETE CASCADE,
                    attending INTEGER NOT NULL CHECK (attending IN (0, 1)),
                    guest_count INTEGER NOT NULL CHECK (guest_count BETWEEN 0 AND 50),
                    updated_at TEXT NOT NULL,
                    CHECK ((attending = 0 AND guest_count = 0)
                        OR (attending = 1 AND guest_count >= 1))
                )
            """)
            connection.execute(
                "INSERT OR IGNORE INTO event (id, data_json) VALUES (1, ?)",
                (DEFAULT_EVENT.model_dump_json(by_alias=True),),
            )
            self.migrate(connection)

    @staticmethod
    def migrate(connection: sqlite3.Connection) -> None:
        # Version 1 is the original three-table store. Adoption never rewrites its data.
        connection.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
        version = connection.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()[0]
        if version > 4:
            raise RuntimeError("Database schema is newer than this application.")
        if version < 1:
            connection.execute("INSERT INTO schema_migrations VALUES (1, ?)", (now_iso(),))
        if version < 2:
            connection.execute("CREATE TABLE event_sections (id INTEGER PRIMARY KEY CHECK (id = 1), data_json TEXT NOT NULL)")
            connection.execute("INSERT INTO event_sections VALUES (1, ?)", (DEFAULT_SECTIONS.model_dump_json(by_alias=True),))
            connection.execute("""
                CREATE TABLE wishes (
                    id TEXT PRIMARY KEY,
                    invitation_id TEXT NOT NULL REFERENCES invitations(id) ON DELETE CASCADE,
                    client_request_id TEXT NOT NULL,
                    author TEXT NOT NULL CHECK (length(author) BETWEEN 1 AND 80),
                    message TEXT NOT NULL CHECK (length(message) BETWEEN 1 AND 600),
                    created_at TEXT NOT NULL,
                    UNIQUE (invitation_id, client_request_id)
                )
            """)
            connection.execute("CREATE INDEX wishes_family_created ON wishes(invitation_id, created_at DESC, id DESC)")
            connection.execute("CREATE INDEX wishes_created ON wishes(created_at DESC, id DESC)")
            connection.execute("INSERT INTO schema_migrations VALUES (2, ?)", (now_iso(),))
        if version < 3:
            connection.execute("""
                CREATE TABLE admin_sessions (
                    token_hash TEXT PRIMARY KEY CHECK (length(token_hash) = 64),
                    csrf_token TEXT NOT NULL CHECK (length(csrf_token) = 43),
                    key_fingerprint TEXT NOT NULL CHECK (length(key_fingerprint) = 64),
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL CHECK (expires_at > created_at)
                )
            """)
            connection.execute("CREATE INDEX admin_sessions_expiry ON admin_sessions(expires_at)")
            connection.execute("INSERT INTO schema_migrations VALUES (3, ?)", (now_iso(),))
        if version < 4:
            # Existing hash-only links remain valid; none is silently regenerated.
            connection.execute("ALTER TABLE invitations ADD COLUMN token_ciphertext TEXT")
            connection.execute("INSERT INTO schema_migrations VALUES (4, ?)", (now_iso(),))

    def create_admin_session(self, key_fingerprint: str, *, lifetime: int = 43_200, now: int | None = None) -> tuple[str, dict[str, str]]:
        timestamp = int(time.time()) if now is None else now
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        expiry = timestamp + lifetime
        with self.transaction(write=True) as connection:
            connection.execute("DELETE FROM admin_sessions WHERE expires_at <= ? OR key_fingerprint != ?", (timestamp, key_fingerprint))
            # Keep at most 20 active sessions. The oldest are revoked on a new login.
            connection.execute("DELETE FROM admin_sessions WHERE token_hash IN (SELECT token_hash FROM admin_sessions ORDER BY created_at DESC, token_hash DESC LIMIT -1 OFFSET 19)")
            connection.execute("INSERT INTO admin_sessions VALUES (?, ?, ?, ?, ?)", (token_hash(token), csrf, key_fingerprint, timestamp, expiry))
        return token, {"csrfToken": csrf, "expiresAt": datetime.fromtimestamp(expiry, timezone.utc).isoformat()}

    def get_admin_session(self, token: str, key_fingerprint: str, *, now: int | None = None) -> dict[str, str] | None:
        if re.fullmatch(r"[A-Za-z0-9_-]{43}", token) is None:
            return None
        timestamp = int(time.time()) if now is None else now
        with self.transaction() as connection:
            row = connection.execute("SELECT csrf_token, key_fingerprint, expires_at FROM admin_sessions WHERE token_hash = ? AND expires_at > ?", (token_hash(token), timestamp)).fetchone()
        if row is None or not secrets.compare_digest(row["key_fingerprint"], key_fingerprint):
            return None
        return {"csrfToken": row["csrf_token"], "expiresAt": datetime.fromtimestamp(row["expires_at"], timezone.utc).isoformat()}

    def revoke_admin_session(self, token: str) -> None:
        if re.fullmatch(r"[A-Za-z0-9_-]{43}", token) is None:
            return
        with self.transaction(write=True) as connection:
            connection.execute("DELETE FROM admin_sessions WHERE token_hash = ?", (token_hash(token),))

    @staticmethod
    def read_event(connection: sqlite3.Connection) -> EventData:
        row = connection.execute("SELECT data_json FROM event WHERE id = 1").fetchone()
        return EventData.model_validate_json(row["data_json"])

    def get_event(self) -> EventData:
        with self.transaction() as connection:
            return self.read_event(connection)

    def replace_event(self, event: EventData) -> EventData:
        with self.transaction(write=True) as connection:
            connection.execute("UPDATE event SET data_json = ? WHERE id = 1", (event.model_dump_json(by_alias=True),))
        return event

    @staticmethod
    def read_sections(connection: sqlite3.Connection) -> SectionsData:
        row = connection.execute("SELECT data_json FROM event_sections WHERE id = 1").fetchone()
        return SectionsData.model_validate_json(row["data_json"])

    def get_sections(self) -> SectionsData:
        with self.transaction() as connection:
            return self.read_sections(connection)

    def replace_sections(self, sections: SectionsData) -> SectionsData:
        with self.transaction(write=True) as connection:
            connection.execute("UPDATE event_sections SET data_json = ? WHERE id = 1", (sections.model_dump_json(by_alias=True),))
        return sections

    def get_public_invitation(self, token: str) -> InvitationResponse:
        digest = token_lookup_hash(token)
        with self.transaction() as connection:
            row = connection.execute(JOIN_INVITATIONS + " WHERE i.token_hash = ? AND i.active = 1", (digest,)).fetchone()
            if row is None:
                raise NotFoundError
            last_wish = connection.execute("SELECT * FROM wishes WHERE invitation_id = ? ORDER BY created_at DESC, id DESC LIMIT 1", (row["id"],)).fetchone()
            return InvitationResponse(
                event=self.read_event(connection),
                invitation=InvitationData(id=row["id"], family_name=row["family_name"], seats=row["seats"]),
                rsvp=rsvp_from_row(row),
                sections=self.read_sections(connection),
                wish=wish_from_row(last_wish) if last_wish is not None else None,
            )

    def save_rsvp(self, token: str, answer: RsvpInput) -> RsvpData:
        digest = token_lookup_hash(token)
        with self.transaction(write=True) as connection:
            row = connection.execute(JOIN_INVITATIONS + " WHERE i.token_hash = ? AND i.active = 1", (digest,)).fetchone()
            if row is None:
                raise NotFoundError
            if answer.guest_count > row["seats"]:
                raise QuotaExceededError
            previous = rsvp_from_row(row)
            if previous is not None and (previous.attending, previous.guest_count) == (answer.attending, answer.guest_count):
                return previous
            response = RsvpData(**answer.model_dump(), updated_at=now_iso())
            connection.execute("""
                INSERT INTO rsvps (invitation_id, attending, guest_count, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(invitation_id) DO UPDATE SET
                    attending = excluded.attending,
                    guest_count = excluded.guest_count,
                    updated_at = excluded.updated_at
            """, (row["id"], int(response.attending), response.guest_count, response.updated_at))
            return response

    def create_invitation(self, invitation: InvitationCreate) -> CreatedInvitation:
        self.link_cipher.require_key()
        token = secrets.token_urlsafe(32)
        identifier = str(uuid4())
        encrypted = self.link_cipher.encrypt(identifier, token)
        timestamp = now_iso()
        with self.transaction(write=True) as connection:
            connection.execute("""
                INSERT INTO invitations (id, family_name, seats, token_hash, active, created_at, updated_at, token_ciphertext)
                VALUES (?, ?, ?, ?, 1, ?, ?, ?)
            """, (identifier, invitation.family_name, invitation.seats, token_hash(token), timestamp, timestamp, encrypted))
        return CreatedInvitation(
            id=identifier,
            family_name=invitation.family_name,
            seats=invitation.seats,
            active=True,
            created_at=timestamp,
            updated_at=timestamp,
            rsvp=None,
            token=token,
            invitation_path=f"/?invitation={token}",
        )

    def list_invitations(self, *, limit: int, offset: int, status: str = "all", q: str = "") -> list[AdminInvitation]:
        clauses = []
        parameters: list[str | int] = []
        if status == "inactive":
            clauses.append("i.active = 0")
        elif status != "all":
            clauses.append("i.active = 1")
            if status != "active":
                clauses.append({"confirmed": "r.attending = 1", "declined": "r.attending = 0", "pending": "r.attending IS NULL"}[status])
        if q:
            clauses.append("i.family_name LIKE ? ESCAPE '\\'")
            parameters.append(literal_search(q))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.transaction() as connection:
            rows = connection.execute(JOIN_INVITATIONS + where + " ORDER BY i.created_at DESC, i.id LIMIT ? OFFSET ?", (*parameters, limit, offset)).fetchall()
            return [admin_from_row(row) for row in rows]

    def save_wish(self, token: str, wish: WishInput) -> WishData:
        digest = token_lookup_hash(token)
        with self.transaction(write=True) as connection:
            family = connection.execute("SELECT id FROM invitations WHERE token_hash = ? AND active = 1", (digest,)).fetchone()
            if family is None:
                raise NotFoundError
            previous = connection.execute("SELECT * FROM wishes WHERE invitation_id = ? AND client_request_id = ?", (family["id"], wish.client_request_id)).fetchone()
            if previous is not None:
                if (previous["author"], previous["message"]) != (wish.author, wish.message):
                    raise WishConflictError
                return wish_from_row(previous)
            count = connection.execute("SELECT COUNT(*) FROM wishes WHERE invitation_id = ?", (family["id"],)).fetchone()[0]
            if count >= MAX_WISHES_PER_INVITATION:
                raise WishLimitError
            timestamp = now_iso()
            response = WishData(id=str(uuid4()), author=wish.author, message=wish.message, created_at=timestamp, updated_at=timestamp)
            connection.execute("INSERT INTO wishes VALUES (?, ?, ?, ?, ?, ?)", (response.id, family["id"], wish.client_request_id, response.author, response.message, response.created_at))
            return response

    def list_wishes(self, *, limit: int, offset: int, q: str = "") -> list[AdminWish]:
        where = " WHERE i.family_name LIKE ? ESCAPE '\\' OR w.author LIKE ? ESCAPE '\\' OR w.message LIKE ? ESCAPE '\\'" if q else ""
        parameters = (literal_search(q),) * 3 if q else ()
        with self.transaction() as connection:
            rows = connection.execute("SELECT w.*, i.family_name FROM wishes w JOIN invitations i ON i.id = w.invitation_id" + where + " ORDER BY w.created_at DESC, w.id DESC LIMIT ? OFFSET ?", (*parameters, limit, offset)).fetchall()
            return [AdminWish(**wish_from_row(row).model_dump(), invitation_id=row["invitation_id"], family_name=row["family_name"]) for row in rows]

    def summary(self) -> AdminSummary:
        with self.transaction() as connection:
            row = connection.execute("""
                SELECT COUNT(*) AS total,
                    COALESCE(SUM(i.active), 0) AS active,
                    COALESCE(SUM(CASE WHEN i.active = 1 AND r.attending = 1 THEN 1 ELSE 0 END), 0) AS confirmed,
                    COALESCE(SUM(CASE WHEN i.active = 1 AND r.attending = 0 THEN 1 ELSE 0 END), 0) AS declined,
                    COALESCE(SUM(CASE WHEN i.active = 1 AND r.attending IS NULL THEN 1 ELSE 0 END), 0) AS pending,
                    COALESCE(SUM(CASE WHEN i.active = 1 AND r.attending = 1 THEN r.guest_count ELSE 0 END), 0) AS guests,
                    COALESCE(SUM(CASE WHEN i.active = 1 THEN i.seats ELSE 0 END), 0) AS seats
                FROM invitations i LEFT JOIN rsvps r ON r.invitation_id = i.id
            """).fetchone()
            wishes = connection.execute("SELECT COUNT(*) FROM wishes").fetchone()[0]
            return AdminSummary(total_invitations=row["total"], active_invitations=row["active"], confirmed_invitations=row["confirmed"], declined_invitations=row["declined"], pending_invitations=row["pending"], confirmed_guests=row["guests"], reserved_seats=row["seats"], total_wishes=wishes)

    def patch_invitation(self, identifier: str, patch: InvitationPatch) -> AdminInvitation:
        with self.transaction(write=True) as connection:
            row = connection.execute(JOIN_INVITATIONS + " WHERE i.id = ?", (identifier,)).fetchone()
            if row is None:
                raise NotFoundError
            family_name = patch.family_name if patch.family_name is not None else row["family_name"]
            seats = patch.seats if patch.seats is not None else row["seats"]
            active = patch.active if patch.active is not None else bool(row["active"])
            response = rsvp_from_row(row)
            if response is not None and response.guest_count > seats:
                raise ConfirmationConflictError
            connection.execute(
                "UPDATE invitations SET family_name = ?, seats = ?, active = ?, updated_at = ? WHERE id = ?",
                (family_name, seats, int(active), now_iso(), identifier),
            )
            updated = connection.execute(JOIN_INVITATIONS + " WHERE i.id = ?", (identifier,)).fetchone()
            return admin_from_row(updated)

    def rotate_token(self, identifier: str) -> RotatedToken:
        self.link_cipher.require_key()
        token = secrets.token_urlsafe(32)
        encrypted = self.link_cipher.encrypt(identifier, token)
        with self.transaction(write=True) as connection:
            cursor = connection.execute("UPDATE invitations SET token_hash = ?, token_ciphertext = ?, updated_at = ? WHERE id = ?", (token_hash(token), encrypted, now_iso(), identifier))
            if cursor.rowcount != 1:
                raise NotFoundError
        return RotatedToken(id=identifier, token=token, invitation_path=f"/?invitation={token}")

    def recover_link(self, identifier: str) -> RotatedToken:
        self.link_cipher.require_key()
        with self.transaction() as connection:
            row = connection.execute("SELECT token_hash, token_ciphertext FROM invitations WHERE id = ?", (identifier,)).fetchone()
        if row is None:
            raise NotFoundError
        if row["token_ciphertext"] is None:
            raise LegacyLinkError
        token = self.link_cipher.decrypt(identifier, row["token_ciphertext"], row["token_hash"])
        return RotatedToken(id=identifier, token=token, invitation_path=f"/?invitation={token}")
