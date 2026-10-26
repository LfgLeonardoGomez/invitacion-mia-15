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
from typing import Iterator
from uuid import uuid4

from .models import (
    AdminInvitation,
    CreatedInvitation,
    DEFAULT_EVENT,
    EventData,
    InvitationCreate,
    InvitationData,
    InvitationPatch,
    InvitationResponse,
    RotatedToken,
    RsvpData,
    RsvpInput,
)


class NotFoundError(Exception):
    """A nonexistent, invalid, or inactive invitation."""


class QuotaExceededError(Exception):
    """The requested response exceeds the invitation's authoritative quota."""


class ConfirmationConflictError(Exception):
    """An administrative change would invalidate an existing response."""


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
    def __init__(self, path: Path) -> None:
        self.path = path

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

    def get_public_invitation(self, token: str) -> InvitationResponse:
        digest = token_lookup_hash(token)
        with self.transaction() as connection:
            row = connection.execute(JOIN_INVITATIONS + " WHERE i.token_hash = ? AND i.active = 1", (digest,)).fetchone()
            if row is None:
                raise NotFoundError
            return InvitationResponse(
                event=self.read_event(connection),
                invitation=InvitationData(id=row["id"], family_name=row["family_name"], seats=row["seats"]),
                rsvp=rsvp_from_row(row),
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
        token = secrets.token_urlsafe(32)
        identifier = str(uuid4())
        timestamp = now_iso()
        with self.transaction(write=True) as connection:
            connection.execute("""
                INSERT INTO invitations (id, family_name, seats, token_hash, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, ?, ?)
            """, (identifier, invitation.family_name, invitation.seats, token_hash(token), timestamp, timestamp))
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

    def list_invitations(self, *, limit: int, offset: int) -> list[AdminInvitation]:
        with self.transaction() as connection:
            rows = connection.execute(JOIN_INVITATIONS + " ORDER BY i.created_at DESC, i.id LIMIT ? OFFSET ?", (limit, offset)).fetchall()
            return [admin_from_row(row) for row in rows]

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
        token = secrets.token_urlsafe(32)
        with self.transaction(write=True) as connection:
            cursor = connection.execute("UPDATE invitations SET token_hash = ?, updated_at = ? WHERE id = ?", (token_hash(token), now_iso(), identifier))
            if cursor.rowcount != 1:
                raise NotFoundError
        return RotatedToken(id=identifier, token=token, invitation_path=f"/?invitation={token}")
