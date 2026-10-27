"""Local preview must not expose private repository files or token-bearing logs."""

from contextlib import contextmanager, redirect_stderr
from http.client import HTTPConnection
import io
from pathlib import Path
import tempfile
from threading import Thread
import unittest

from scripts.serve_frontend import create_server, validate_api_base


class FrontendServerTests(unittest.TestCase):
    @contextmanager
    def server(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("public invitation", encoding="utf-8")
            (root / "admin.html").write_text("public shell only", encoding="utf-8")
            (root / ".env").write_text("secret", encoding="utf-8")
            (root / "backend").mkdir()
            (root / "backend" / "private.sqlite3").write_text("secret", encoding="utf-8")
            server = create_server(0, root=root, api_base="http://127.0.0.1:8000")
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                yield server, root
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def request(self, server, path, method="GET"):
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        try:
            connection.request(method, path)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_public_routes_and_generated_config_no_credentials_or_query_logs(self):
        logs = io.StringIO()
        with redirect_stderr(logs), self.server() as (server, _):
            status, headers, body = self.request(server, "/?invitation=private-token")
            self.assertEqual(status, 200)
            self.assertEqual(body, b"public invitation")
            self.assertEqual(headers["Referrer-Policy"], "no-referrer")
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertEqual(self.request(server, "/admin.html")[0], 200)
            status, _, config = self.request(server, "/app-config.js")
            self.assertEqual(status, 200)
            self.assertIn(b'"apiBaseUrl": "http://127.0.0.1:8000"', config)
            self.assertNotIn(b"private-token", config)
            self.assertNotIn(b"ADMIN", config)
            self.assertEqual(self.request(server, "/index.html", "HEAD")[2], b"")
        self.assertEqual(logs.getvalue(), "")

    def test_allowlist_blocks_private_files_directory_listing_and_traversal(self):
        with self.server() as (server, _):
            for path in ["/.env", "/backend/private.sqlite3", "/assets/", "/../.env", "/%2e%2e/.env", "/backend/../.env", "/.git/config", "/README.md", "/assets/reference.mp4", "/index.html/extra"]:
                with self.subTest(path=path):
                    status, _, body = self.request(server, path)
                    self.assertEqual(status, 404)
                    self.assertEqual(body, b"")

    def test_missing_allowlisted_file_is_generic_404(self):
        with self.server() as (server, _):
            self.assertEqual(self.request(server, "/admin.js")[0], 404)

    def test_api_config_rejects_cleartext_remote_urls_and_credentials(self):
        self.assertIsNone(validate_api_base(None))
        self.assertEqual(validate_api_base("https://api.example.com/base/"), "https://api.example.com/base")
        for value in ["http://api.example.com", "https://user:password@api.example.com", "https://api.example.com/?key=secret", "https://api.example.com/#fragment", "javascript:alert(1)", "//example.com", "https://api.example.com:bad", "https://api.example.com/\n", "https://example.com\\evil"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_api_base(value)


if __name__ == "__main__":
    unittest.main()
