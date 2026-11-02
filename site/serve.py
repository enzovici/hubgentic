"""Local preview of the marketing site, mirroring production routing.

Serves site/dist/ (rebuilt whenever content, templates or static files change)
and forwards POST /lead to the web app, like Caddy does in production.
Run with `make site-dev`; the app must be running for the form to work.
"""
from __future__ import annotations

import http.client
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from build import DIST, ROOT, build

PORT = int(os.environ.get("PORT", "8080"))
APP = os.environ.get("HUBGENTIC_APP", "127.0.0.1:8000")
SOURCES = [ROOT / "content", ROOT / "templates", ROOT / "static"]
_built_at = 0.0


def rebuild_if_stale() -> None:
    global _built_at
    newest = max(p.stat().st_mtime for d in SOURCES for p in d.rglob("*") if p.is_file())
    if newest > _built_at:
        build()
        _built_at = newest


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        rebuild_if_stale()
        path = self.translate_path(self.path)
        if not Path(path).exists() and not self.path.split("?")[0].endswith("/"):
            self.send_response(404)
            body = (DIST / "404.html").read_bytes()
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def do_POST(self) -> None:
        if self.path != "/lead":
            self.send_error(405)
            return
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        conn = http.client.HTTPConnection(APP, timeout=10)
        headers = {k: v for k, v in self.headers.items() if k.lower() not in ("connection",)}
        conn.request("POST", "/lead", body, headers)  # Host is passed through, as Caddy does
        resp = conn.getresponse()
        data = resp.read()
        self.send_response(resp.status)
        for k, v in resp.getheaders():
            if k.lower() not in ("transfer-encoding", "connection", "content-length"):
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    rebuild_if_stale()
    print(f"hubgentic site on http://localhost:{PORT} (lead form → {APP})")
    ThreadingHTTPServer(("127.0.0.1", PORT), partial(Handler, directory=str(DIST))).serve_forever()
