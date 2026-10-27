"""Railway-only entrypoint: refuse ephemeral SQLite or missing production secrets."""

import os
from pathlib import Path
import sys


def validate_runtime(environment: dict[str, str]) -> int:
    mount = environment.get("RAILWAY_VOLUME_MOUNT_PATH", "")
    database = environment.get("MIA_DATABASE_PATH", "")
    if not mount or not database:
        raise ValueError("A Railway volume and MIA_DATABASE_PATH are required.")
    volume_path = Path(mount).resolve(strict=True)
    db_path = Path(database)
    if not db_path.is_absolute() or not db_path.resolve().is_relative_to(volume_path):
        raise ValueError("SQLite must be inside the attached persistent volume.")
    if db_path.resolve() == volume_path or not volume_path.is_dir():
        raise ValueError("SQLite requires a file path inside the volume directory.")
    if not environment.get("MIA_ADMIN_API_KEY") or not environment.get("MIA_LINK_ENCRYPTION_KEY"):
        raise ValueError("Both production secrets are required.")
    if environment.get("MIA_ENABLE_DOCS", "false").lower() not in {"false", "0"}:
        raise ValueError("Public API documentation must remain disabled.")
    port = int(environment.get("PORT", "8000"))
    if not 1 <= port <= 65535:
        raise ValueError("Invalid listening port.")
    return port


def main() -> None:
    port = validate_runtime(dict(os.environ))
    # Settings validates secret formats and explicit origins without logging values.
    from app.config import Settings

    Settings.from_environment()
    os.umask(0o077)
    os.execv(sys.executable, [
        sys.executable, "-m", "uvicorn", "app.main:app",
        "--host", "0.0.0.0", "--port", str(port), "--workers", "1",
        "--no-access-log", "--no-proxy-headers",
    ])


if __name__ == "__main__":
    main()
