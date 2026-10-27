"""The public artifact must never be the repository root."""

from pathlib import Path
import json
import re
import tempfile
import unittest

from scripts.prepare_pages import PUBLIC_FILES, ROOT, prepare_pages


class PublicArtifactTests(unittest.TestCase):
    def test_vercel_uses_allowlist_and_explicit_api_proxy(self):
        config = json.loads((ROOT / "vercel.json").read_text("utf-8"))
        self.assertEqual(config["outputDirectory"], "public")
        self.assertIn("--same-origin-api", config["buildCommand"])
        self.assertEqual(config["rewrites"], [{
            "source": "/api/:path*",
            "destination": "https://invitacion-mia-15-production.up.railway.app/api/:path*",
        }])
        api_headers = next(item["headers"] for item in config["headers"] if item["source"] == "/api/:path*")
        self.assertIn({"key": "Cache-Control", "value": "private, no-store"}, api_headers)

    def test_same_origin_config_only_changes_generated_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            self.populate(source)
            target = Path(directory) / "site"
            original = (source / "app-config.js").read_bytes()
            prepare_pages(target, source, same_origin_api=True)
            self.assertIn("apiBaseUrl: ''", (target / "app-config.js").read_text("utf-8"))
            self.assertEqual((source / "app-config.js").read_bytes(), original)
            self.assertFalse((target / "backend").exists())

    def populate(self, source):
        for relative in PUBLIC_FILES:
            path = source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"public: {relative}".encode())

    def test_only_explicit_public_files_are_copied(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            target = Path(directory) / "site"
            self.populate(source)
            for private in [".env", "backend/app/main.py", "backend/data/invitations.sqlite3", "assets/reference.mp4", "README.md"]:
                path = source / private
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("not public", encoding="utf-8")
            prepared = prepare_pages(target, source)
            actual = {path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file()}
            self.assertEqual(actual, set(PUBLIC_FILES) | {".nojekyll"})
            self.assertEqual(set(prepared), actual)
            for relative in PUBLIC_FILES:
                self.assertEqual((source / relative).read_bytes(), (target / relative).read_bytes())

    def test_missing_public_resource_fails_before_creating_site(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            self.populate(source)
            (source / PUBLIC_FILES[-1]).unlink()
            target = Path(directory) / "site"
            with self.assertRaises(FileNotFoundError):
                prepare_pages(target, source)
            self.assertFalse(target.exists())

    def test_existing_destination_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            sentinel = target / "keep.txt"
            sentinel.write_text("keep", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                prepare_pages(target)
            self.assertEqual(sentinel.read_text("utf-8"), "keep")

    def test_current_local_references_are_in_the_allowlist(self):
        html = (ROOT / "index.html").read_text("utf-8") + (ROOT / "admin.html").read_text("utf-8")
        playlist = (ROOT / "music-playlist.js").read_text("utf-8")
        references = re.findall(r'src="(\./[^\"]+)"', html)
        references += re.findall(r"src:\s*'(\./[^']+)'", playlist)
        for reference in references:
            self.assertIn(reference.removeprefix("./").split("?")[0], PUBLIC_FILES)
        for reference in re.findall(r'href="(\./[^\"]+\.css(?:\?[^\"]*)?)"', html):
            self.assertIn(reference.removeprefix("./").split("?")[0], PUBLIC_FILES)


if __name__ == "__main__":
    unittest.main()
