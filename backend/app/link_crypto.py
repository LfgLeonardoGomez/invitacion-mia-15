"""Authenticated encryption for recoverable links; the key never belongs in SQLite."""

import hashlib
import json
import re
import secrets

from cryptography.fernet import Fernet, InvalidToken


class LinkUnavailableError(Exception):
    """Encryption is not configured or a stored envelope cannot be trusted."""


class LegacyLinkError(Exception):
    """A historical invitation retained only its irreversible lookup hash."""


def validate_link_key(key: str) -> None:
    if not isinstance(key, str) or re.fullmatch(r"[A-Za-z0-9_-]{43}=", key) is None:
        raise ValueError("MIA_LINK_ENCRYPTION_KEY must be a separate, generated Fernet key.")
    try:
        Fernet(key)
    except (ValueError, TypeError):
        raise ValueError("MIA_LINK_ENCRYPTION_KEY must be a separate, generated Fernet key.") from None


class LinkCipher:
    def __init__(self, key: str | None):
        if key is not None:
            validate_link_key(key)
        self._cipher = Fernet(key) if key is not None else None

    def require_key(self) -> Fernet:
        if self._cipher is None:
            raise LinkUnavailableError
        return self._cipher

    def encrypt(self, identifier: str, token: str) -> str:
        cipher = self.require_key()
        envelope = json.dumps({"id": identifier, "token": token}, separators=(",", ":")).encode("ascii")
        return cipher.encrypt(envelope).decode("ascii")

    def decrypt(self, identifier: str, ciphertext: str, expected_hash: str) -> str:
        cipher = self.require_key()
        try:
            if not isinstance(ciphertext, str) or len(ciphertext) > 4096:
                raise LinkUnavailableError
            data = json.loads(cipher.decrypt(ciphertext.encode("ascii")))
            if not isinstance(data, dict) or set(data) != {"id", "token"} or data["id"] != identifier:
                raise LinkUnavailableError
            token = data["token"]
            if not isinstance(token, str) or re.fullmatch(r"[A-Za-z0-9_-]{43}", token) is None:
                raise LinkUnavailableError
            digest = hashlib.sha256(token.encode("ascii")).hexdigest()
            if not secrets.compare_digest(digest, expected_hash):
                raise LinkUnavailableError
            return token
        except (InvalidToken, ValueError, TypeError, UnicodeError, KeyError):
            # Never include key, ciphertext, plaintext, or JSON errors in logs/responses.
            raise LinkUnavailableError from None
