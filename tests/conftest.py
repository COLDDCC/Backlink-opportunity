import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest


class FixtureServer:
    """Minimal HTTP server so prober tests don't need real internet access.

    Register routes with `.routes[path] = (status, body)` before starting,
    or mutate `.routes` at any time (the handler reads it live).
    """

    def __init__(self):
        self.routes: dict[str, tuple[int, str]] = {}
        handler = self._make_handler()
        self.httpd = HTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def _make_handler(self):
        routes = self.routes

        class Handler(BaseHTTPRequestHandler):
            def _respond(self):
                status, body = routes.get(self.path, (404, "not found"))
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body.encode("utf-8"))

            def do_GET(self):
                self._respond()

            def do_HEAD(self):
                self._respond()

            def log_message(self, *args):
                pass  # keep test output quiet

        return Handler

    @property
    def base_url(self) -> str:
        host, port = self.httpd.server_address
        return f"http://{host}:{port}"

    def start(self):
        self.thread.start()

    def stop(self):
        self.httpd.shutdown()
        self.thread.join(timeout=5)


@pytest.fixture
def fixture_server():
    server = FixtureServer()
    server.start()
    yield server
    server.stop()
