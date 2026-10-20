import threading
import urllib.error
import urllib.request

import pytest

from oracle_lab.web.http import Request, Response
from oracle_lab.web.middleware import ClientAddress
from oracle_lab.web.server import create_server


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


@pytest.fixture
def serve_app():
    servers = []

    def start(app):
        httpd = create_server(app, "127.0.0.1", 0)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        servers.append(httpd)
        opener = urllib.request.build_opener(_NoRedirect)

        def get(path):
            try:
                resp = opener.open(f"http://127.0.0.1:{httpd.server_port}{path}")
            except urllib.error.HTTPError as err:  # a 302 surfaces as an HTTPError without the redirect handler
                resp = err
            with resp:
                return resp.status, resp.headers, resp.read()

        return get

    yield start
    for httpd in servers:
        httpd.shutdown()
        httpd.server_close()


def test_client_address_ignores_forwarded_for_unless_trusted():
    seen = []

    def handler(r):
        seen.append(r.client)
        return Response()

    req = Request("GET", "/", {"x-forwarded-for": "6.6.6.6, 1.2.3.4"}, client="10.0.0.1")
    ClientAddress(trust_proxy=False)(req, handler)
    ClientAddress(trust_proxy=True)(req, handler)
    assert seen == ["10.0.0.1", "1.2.3.4"]


def test_redirect_and_cookies_reach_the_wire(serve_app):
    get = serve_app(lambda r: Response.redirect("/login", cookies=["a=1; Path=/", "b=2; Path=/"]))
    status, headers, _ = get("/x")
    assert status == 302 and headers["Location"] == "/login"
    assert headers.get_all("Set-Cookie") == ["a=1; Path=/", "b=2; Path=/"]
