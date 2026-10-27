"""Copy an explicit public-file allowlist for Pages. No build, no backend files."""

import argparse
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_FILES = (
    "index.html",
    "app-config.js",
    "admin.html",
    "admin.css",
    "admin.js",
    "invitation-data.js",
    "invitation-sections.js",
    "music-player.js",
    "music-playlist.js",
    "assets/Reino de Linternas sobre el Lago.png",
    "assets/Tiara Real de Oro y Gemas Facetadas.png",
    "assets/mia-soundtrack.mp3",
    "assets/mia-my-one-and-only-love.mp3",
    "assets/mia-understand.mp3",
)


def prepare_pages(destination: Path, source: Path = ROOT) -> tuple[str, ...]:
    source = source.resolve(strict=True)
    destination = destination.absolute()
    if destination.exists():
        raise FileExistsError("Use a new destination directory; existing content is never removed.")
    for relative in PUBLIC_FILES:
        path = source / relative
        resolved = path.resolve(strict=True)
        if path.is_symlink() or not resolved.is_relative_to(source) or not path.is_file():
            raise ValueError(f"Expected a regular public file within the project: {relative}")
    destination.mkdir(parents=True, exist_ok=False)
    for relative in PUBLIC_FILES:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, target)
    (destination / ".nojekyll").write_text("", encoding="utf-8")
    return (*PUBLIC_FILES, ".nojekyll")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    files = prepare_pages(args.destination)
    print(f"Prepared {len(files)} public files without a build.")
