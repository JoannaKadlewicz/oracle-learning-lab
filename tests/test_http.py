import base64
import hashlib
import re
import threading
import urllib.error
import urllib.request

import pytest

from oracle_lab.web.http import HttpError, Request, Response
from oracle_lab.web.middleware import ClientAddress, SecurityHeaders
from oracle_lab.web.server import create_server
from oracle_lab.web.static import StaticFiles, inline_script_hashes


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


def test_every_response_carries_the_security_headers():
    resp = SecurityHeaders(hsts=True, inline_script_hashes=("sha256-abc=",))(Request("GET", "/", {}), lambda r: Response())
    csp = resp.headers["Content-Security-Policy"]
    for part in ("default-src 'self'", "script-src 'self' https://cdnjs.cloudflare.com 'sha256-abc='",
                 "frame-ancestors 'none'", "form-action 'self' https://accounts.google.com", "object-src 'none'",
                 "base-uri 'none'", "font-src https://fonts.gstatic.com"):
        assert part in csp
    assert "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com" in csp
    assert resp.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"
    assert resp.headers["X-Frame-Options"] == "DENY" and resp.headers["Referrer-Policy"] == "same-origin"
    assert resp.headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert "camera=()" in resp.headers["Permissions-Policy"]
    assert "Strict-Transport-Security" not in SecurityHeaders(False, ())(Request("GET", "/", {}), lambda r: Response()).headers


def test_inline_script_hash_matches_the_page():
    h = inline_script_hashes("<script>let a=1;</script><script src='/x.js'></script>")
    assert h == ("sha256-" + base64.b64encode(hashlib.sha256(b"let a=1;").digest()).decode(),)


def test_html_pages_are_never_cached(tmp_path):
    (tmp_path / "index.html").write_text("<p>hi</p>")
    (tmp_path / "app.js").write_text("1")
    static = StaticFiles(tmp_path)
    assert static(Request("GET", "/", {})).headers["Cache-Control"] == "no-store"
    assert static(Request("GET", "/app.js", {})).headers["Cache-Control"] == "no-cache"


def test_every_cdn_script_and_stylesheet_has_an_integrity_hash():
    from oracle_lab.resources import STATIC_DIR
    page = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    tags = [t for t in re.findall(r"<(?:script|link)\b[^>]*>", page) if "cdnjs.cloudflare.com" in t]
    assert len(tags) >= 9
    for tag in tags:
        assert re.search(r'integrity="sha384-[A-Za-z0-9+/]+=*"', tag) and 'crossorigin="anonymous"' in tag, tag


@pytest.mark.parametrize("path", ["/css/../index.html", "/./index.html", "//index.html", "/css/%2e%2e/index.html"])
def test_static_files_refuse_dot_segments(tmp_path, path):
    (tmp_path / "css").mkdir()
    (tmp_path / "index.html").write_text("<html></html>")
    with pytest.raises(HttpError) as err:
        StaticFiles(tmp_path)(Request("GET", path, {}))
    assert err.value.status == 404
