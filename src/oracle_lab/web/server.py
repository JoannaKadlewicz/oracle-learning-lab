"""Serve a WebApplication with the standard library's threading HTTP server."""

from __future__ import annotations

import logging
import signal
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from oracle_lab import __version__
from oracle_lab.i18n import negotiate, translate
from oracle_lab.web.application import WebApplication
from oracle_lab.web.http import Request, Response

log = logging.getLogger(__name__)

MAX_BODY_BYTES = 2 * 1024 * 1024  # SQL scripts and answers are small; refuse anything absurd


def handler_for(app: WebApplication) -> type[BaseHTTPRequestHandler]:
    """A request handler class bound to `app` (http.server instantiates one per request)."""

    class RequestHandler(BaseHTTPRequestHandler):
        server_version = f"OracleLearningLab/{__version__}"
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 - name required by BaseHTTPRequestHandler
            self._dispatch()

        def do_POST(self) -> None:  # noqa: N802
            self._dispatch()

        def _dispatch(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY_BYTES:
                lang = negotiate(self.headers.get("X-Language"), self.headers.get("Accept-Language"))
                self._write(Response.json({"error": translate(lang, "Request body too large")}, 413))
                self.close_connection = True
                return
            body = self.rfile.read(length) if length else b""
            headers = {k.lower(): v for k, v in self.headers.items()}
            self._write(app(Request(self.command, self.path, headers, body, client=self.client_address[0])))

        def _write(self, response: Response) -> None:
            self.send_response(response.status)
            self.send_header("Content-Type", response.content_type)
            self.send_header("Content-Length", str(len(response.body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            for name, value in response.headers.items():
                self.send_header(name, value)
            for cookie in response.cookies:
                self.send_header("Set-Cookie", cookie)
            self.end_headers()
            self.wfile.write(response.body)

        def log_message(self, fmt: str, *args) -> None:
            log.debug(fmt, *args)  # requests are logged by the access_log middleware

    return RequestHandler


def create_server(app: WebApplication, host: str, port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), handler_for(app))
    server.daemon_threads = True
    return server


def serve(app: WebApplication, host: str, port: int) -> None:
    """Serve until SIGINT or SIGTERM, then finish the requests in flight and return."""
    server = create_server(app, host, port)

    def stop(signum: int, _frame) -> None:
        log.info("received %s, shutting down", signal.Signals(signum).name)
        threading.Thread(target=server.shutdown, daemon=True).start()

    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, stop)
    try:
        server.serve_forever()
    finally:
        server.server_close()
