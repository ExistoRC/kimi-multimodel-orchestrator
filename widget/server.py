from __future__ import annotations

import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

from .config import clear_runtime, write_runtime
from .state import StateStore

MAX_BODY = 4 * 1024 * 1024


class StatusHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, store: StateStore, callback: Callable[[str, Any], None]) -> None:
        super().__init__(("127.0.0.1", 0), StatusHandler)
        self.store = store
        self.callback = callback
        self.token = secrets.token_urlsafe(32)


class StatusHandler(BaseHTTPRequestHandler):
    server: StatusHTTPServer

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _authorized(self) -> bool:
        expected_host = f"127.0.0.1:{self.server.server_port}"
        return self.headers.get("Host") == expected_host and self.headers.get("Authorization") == f"Bearer {self.server.token}"

    def _json(self, status: int, value: Any) -> None:
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if not self._authorized():
            self._json(401, {"ok": False})
            return
        if self.path == "/health":
            self._json(200, {"ok": True, "version": "0.5.1"})
        elif self.path == "/api/state":
            self._json(200, self.server.store.snapshot())
        else:
            self._json(404, {"ok": False})

    def do_POST(self) -> None:
        if not self._authorized():
            self._json(401, {"ok": False})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json(400, {"ok": False})
            return
        if length <= 0 or length > MAX_BODY:
            self._json(413, {"ok": False})
            return
        try:
            payload = json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            self._json(400, {"ok": False})
            return
        if self.path == "/event" and isinstance(payload, dict):
            self.server.store.apply(payload)
            self.server.callback("event", None)
            self._json(200, {"ok": True})
        elif self.path == "/command" and isinstance(payload, dict):
            action = payload.get("action")
            if action not in {"show", "hide", "settings", "quit"}:
                self._json(400, {"ok": False})
                return
            self.server.callback("command", action)
            self._json(200, {"ok": True})
        else:
            self._json(404, {"ok": False})


class StatusService:
    def __init__(self, store: StateStore, callback: Callable[[str, Any], None]) -> None:
        self.server = StatusHTTPServer(store, callback)
        self.thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return self.server.server_port

    @property
    def token(self) -> str:
        return self.server.token

    def start(self) -> None:
        write_runtime(self.port, self.token)
        self.thread = threading.Thread(target=self.server.serve_forever, name="kimi-widget-http", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        clear_runtime(self.token)
        self.server.shutdown()
        self.server.server_close()
        if self.thread:
            self.thread.join(timeout=2)
