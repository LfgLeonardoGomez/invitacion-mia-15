"""Loopback-only development server. Explicit public files, never the repository.

Not a production server. API runs separately; configure its explicit CORS origin.
Requests are deliberately not logged: invitation query strings are credentials.
"""

import argparse
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import shutil
from urllib.parse import unquote, urlsplit

if __package__:
    from .prepare_pages import PUBLIC_FILES, ROOT
else:
    from prepare_pages import PUBLIC_FILES, ROOT


def validate_api_base(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = urlsplit(value)
    try:
        parsed.port
    except ValueError as error:
        raise ValueError("Invalid API port.") from error
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or any(char.isspace() or ord(char) < 32 for char in value)
        or "\\" in value
        or (parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"})
    ):
        raise ValueError("API URL must be HTTPS, or HTTP on loopback, without credentials/query/fragment.")
    return value.rstrip("/")


class FrontendHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, root: Path = ROOT, api_base: str | None = None, **kwargs):
        self.root = root.resolve(strict=True)
        self.api_base = validate_api_base(api_base)
        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):
        # Even failures may contain a private token. Never log the request line.
        pass

    def do_GET(self):
        self.respond(send_body=True)

    def do_HEAD(self):
        self.respond(send_body=False)

    def send_frontend_headers(self, status: int, content_type: str, length: int):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()

    def respond(self, *, send_body: bool):
        try:
            path = unquote(urlsplit(self.path).path, errors="strict")
        except (ValueError, UnicodeError):
            path = ""
        relative = "index.html" if path == "/" else path.removeprefix("/")
        if relative not in PUBLIC_FILES:
            self.send_frontend_headers(404, "text/plain; charset=utf-8", 0)
            return
        if relative == "app-config.js":
            body = ("window.MIA_CONFIG = Object.freeze(" + json.dumps({
                "apiBaseUrl": self.api_base, "invitationBaseUrl": None,
            }) + ");\n").encode("utf-8")
            self.send_frontend_headers(200, "text/javascript; charset=utf-8", len(body))
            if send_body:
                self.wfile.write(body)
            return
        file = self.root / relative
        try:
            resolved = file.resolve(strict=True)
            # Reject symlinked files AND parent directories outside the project.
            if file.is_symlink() or not resolved.is_relative_to(self.root) or not file.is_file():
                raise FileNotFoundError
            source = file.open("rb")
        except (FileNotFoundError, PermissionError, OSError):
            self.send_frontend_headers(404, "text/plain; charset=utf-8", 0)
            return
        with source:
            content_type = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
            if file.suffix in {".js", ".html", ".css"}:
                content_type = {".js": "text/javascript", ".html": "text/html", ".css": "text/css"}[file.suffix] + "; charset=utf-8"
            self.send_frontend_headers(200, content_type, file.stat().st_size)
            try:
                if send_body:
                    shutil.copyfileobj(source, self.wfile)
            except (BrokenPipeError, ConnectionResetError):
                self.close_connection = True


def create_server(port: int = 5173, *, api_base: str | None = None, root: Path = ROOT):
    api_base = validate_api_base(api_base)
    return ThreadingHTTPServer(("127.0.0.1", port), partial(FrontendHandler, root=root, api_base=api_base))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=5173)
    parser.add_argument("--api-base-url", default=None, help="Public API base, WITHOUT /api; omit for mock preview.")
    args = parser.parse_args()
    try:
        server = create_server(args.port, api_base=args.api_base_url)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(f"Frontend: http://127.0.0.1:{server.server_port}/ | Panel: /admin.html", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
