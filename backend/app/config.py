"""Explicit, fail-closed environment configuration (no development secrets)."""

from dataclasses import dataclass, field
import os
from pathlib import Path
from urllib.parse import urlsplit


DEFAULT_DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "invitations.sqlite3"


@dataclass(frozen=True, slots=True)
class Settings:
    database_path: Path = field(default_factory=lambda: DEFAULT_DATABASE_PATH)
    admin_api_key: str | None = None
    allowed_origins: tuple[str, ...] = ()
    enable_docs: bool = False

    def __post_init__(self) -> None:
        database_path = Path(self.database_path)
        if str(database_path) == ":memory:":
            raise ValueError("Use an on-disk SQLite path; each operation has its own connection.")
        object.__setattr__(self, "database_path", database_path)
        if self.admin_api_key is not None:
            if not 32 <= len(self.admin_api_key) <= 256 or any(
                not 33 <= ord(character) <= 126 for character in self.admin_api_key
            ):
                raise ValueError("MIA_ADMIN_API_KEY must contain 32–256 printable ASCII characters, without spaces.")
        origins = []
        for origin in self.allowed_origins:
            origin = origin.strip().rstrip("/")
            parsed = urlsplit(origin)
            if (
                "*" in origin
                or parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("MIA_ALLOWED_ORIGINS accepts explicit HTTP(S) origins only.")
            try:
                parsed.port
            except ValueError as exc:
                raise ValueError("Invalid port in MIA_ALLOWED_ORIGINS.") from exc
            origins.append(origin)
        object.__setattr__(self, "allowed_origins", tuple(dict.fromkeys(origins)))

    @classmethod
    def from_environment(cls) -> "Settings":
        docs = os.getenv("MIA_ENABLE_DOCS", "false").lower()
        if docs not in {"true", "false", "1", "0"}:
            raise ValueError("MIA_ENABLE_DOCS must be true or false.")
        return cls(
            database_path=Path(os.getenv("MIA_DATABASE_PATH") or str(DEFAULT_DATABASE_PATH)),
            admin_api_key=os.getenv("MIA_ADMIN_API_KEY") or None,
            allowed_origins=tuple(filter(None, os.getenv("MIA_ALLOWED_ORIGINS", "").split(","))),
            enable_docs=docs in {"true", "1"},
        )
