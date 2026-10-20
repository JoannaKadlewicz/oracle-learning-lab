"""Google sign-in: OpenID Connect authorization-code flow with PKCE, state and nonce.

The ID token arrives straight from Google's token endpoint over verified TLS, so (per the design, section 3)
its signature is not checked; issuer, audience, expiry, nonce and verified email are.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import http.client
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from oracle_lab.accounts.repositories import AppStores
from oracle_lab.auth.audit import AuditLog
from oracle_lab.auth.models import AuthError, EmailTaken, Identity, LoginFlow, LoginRequired, Principal
from oracle_lab.auth.registration import Registration
from oracle_lab.auth.sessions import SessionManager
from oracle_lab.auth.throttle import Throttle
from oracle_lab.auth.tokens import new_id, new_token, normalise_email
from oracle_lab.config import GoogleConfig
from oracle_lab.credentials import Secret
from oracle_lab.services import Clock

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
CALLBACK_PATH = "/auth/google/callback"
GENERIC = "Sign-in did not complete. Please try again."
EMAIL_EXISTS = ("An account with this email already exists. Sign in with your password, "
                "then connect Google in Settings.")
FLOW_TTL = 600
REAUTH_SECONDS = 300
_ISSUERS = ("https://accounts.google.com", "accounts.google.com")
_CLOCK_SKEW = 60
_NAME_LIMIT = 80
_MAX_EMAIL = 254


class GoogleError(Exception):
    """A failed exchange or an unacceptable ID token. Messages are fixed text: never a code, token or body."""


class TokenEndpoint(Protocol):
    def exchange(self, code: str, code_verifier: str, redirect_uri: str) -> dict: ...


class HttpTokenEndpoint:
    def __init__(self, client_id: str, client_secret: Secret, timeout: float = 10):
        self._client_id = client_id
        self._client_secret = client_secret
        self._timeout = timeout

    def exchange(self, code: str, code_verifier: str, redirect_uri: str) -> dict:
        data = urllib.parse.urlencode({
            "code": code, "client_id": self._client_id, "client_secret": self._client_secret.reveal(),
            "redirect_uri": redirect_uri, "grant_type": "authorization_code", "code_verifier": code_verifier,
        }).encode()
        request = urllib.request.Request(TOKEN_URL, data=data, method="POST",
                                         headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urllib.request.urlopen(request, timeout=self._timeout,  # noqa: S310 - fixed https URL
                                        context=ssl.create_default_context()) as response:
                if response.status != 200:
                    raise GoogleError("token endpoint refused the code")
                body = json.loads(response.read())
        except urllib.error.HTTPError:
            raise GoogleError("token endpoint refused the code") from None
        except (urllib.error.URLError, OSError, TimeoutError, http.client.HTTPException):
            raise GoogleError("token endpoint unreachable") from None
        except ValueError:
            raise GoogleError("token endpoint sent invalid JSON") from None
        if not isinstance(body, dict):
            raise GoogleError("token endpoint sent invalid JSON")
        return body


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def id_token_claims(id_token: str) -> dict:
    """The payload of an ID token (no signature check)."""
    if not isinstance(id_token, str):
        raise GoogleError("malformed id_token")
    parts = id_token.split(".")
    if len(parts) != 3:
        raise GoogleError("malformed id_token")
    try:
        payload = base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4))
        claims = json.loads(payload)
    except ValueError:  # binascii.Error, UnicodeDecodeError and JSONDecodeError are all ValueErrors
        raise GoogleError("malformed id_token") from None
    if not isinstance(claims, dict):
        raise GoogleError("malformed id_token")
    return claims


def validate_claims(claims: dict, client_id: str, nonce: str, now: float) -> None:
    if claims.get("iss") not in _ISSUERS:
        raise GoogleError("bad issuer")
    aud = claims.get("aud")
    if isinstance(aud, list):
        if client_id not in aud or claims.get("azp") != client_id:
            raise GoogleError("bad audience")
    elif aud != client_id:
        raise GoogleError("bad audience")
    if "azp" in claims and claims["azp"] != client_id:
        raise GoogleError("bad authorized party")
    exp = claims.get("exp")
    if isinstance(exp, bool) or not isinstance(exp, int | float) or exp + _CLOCK_SKEW <= now:
        raise GoogleError("expired")
    got = claims.get("nonce")
    if not isinstance(got, str) or not hmac.compare_digest(got.encode(), nonce.encode()):
        raise GoogleError("bad nonce")
    if claims.get("email_verified") is not True:
        raise GoogleError("email not verified")


def _local_path(path: str) -> str:
    """Defence in depth (the caller sanitises too): only a same-origin absolute path survives."""
    if (not isinstance(path, str) or not path.startswith("/") or path.startswith(("//", "/\\"))
            or any(not c.isprintable() for c in path)):
        return "/"
    return path


@dataclass(frozen=True)
class GoogleOutcome:
    token: str | None
    next_path: str
    message: str | None


class GoogleSignIn:
    """`registration` is the password flow's Registration: sign-up goes through its create_user, so both flows
    share one lock, the cap, the first-admin rule and the on_user_created hook."""

    def __init__(self, config: GoogleConfig, public_url: str, endpoint: TokenEndpoint, stores: AppStores,
                 sessions: SessionManager, throttle: Throttle, audit: AuditLog, clock: Clock,
                 registration: Registration):
        self._config = config
        self._redirect_uri = public_url.rstrip("/") + CALLBACK_PATH
        self._endpoint = endpoint
        self._stores = stores
        self._sessions = sessions
        self._throttle = throttle
        self._audit = audit
        self._clock = clock
        self._registration = registration

    def start(self, intent: str, next_path: str, principal: Principal | None, ip: str) -> tuple[str, str]:
        self._throttle.check_google(ip)
        if intent not in ("login", "link", "reauth"):
            raise ValueError(f"invalid intent: {intent!r}")
        if intent != "login" and principal is None:
            raise LoginRequired("Login required")
        verifier, state, nonce = new_token(), new_token(), new_token()
        flow = LoginFlow(new_id(), state, nonce, verifier, intent,  # type: ignore[arg-type]
                         principal.user_id if intent != "login" and principal else None, _local_path(next_path),
                         self._clock() + FLOW_TTL)
        self._stores.flows.add(flow)
        query = urllib.parse.urlencode({
            "client_id": self._config.client_id, "redirect_uri": self._redirect_uri, "response_type": "code",
            "scope": "openid email profile", "prompt": "select_account", "state": state, "nonce": nonce,
            "code_challenge": _b64url(hashlib.sha256(verifier.encode()).digest()),
            "code_challenge_method": "S256",
        })
        return f"{AUTH_URL}?{query}", flow.id

    def finish(self, flow_id: str, state: str, code: str, ip: str, user_agent: str,
               current: Principal | None) -> GoogleOutcome:
        flow = self._stores.flows.take(flow_id)
        event = f"google_{flow.intent}" if flow else "google_login"
        user_id = flow.user_id if flow else None

        def fail(reason: str, message: str = GENERIC) -> GoogleOutcome:
            self._audit.record(event, "fail", user_id=user_id, ip=ip, user_agent=user_agent, reason=reason)
            return GoogleOutcome(None, "/login", message)

        if flow is None or flow.expires_at <= self._clock():
            return fail("flow")
        if not hmac.compare_digest(str(state).encode(), flow.state.encode()):
            return fail("state")
        if flow.intent != "login" and (current is None or current.user_id != flow.user_id):
            return fail("session")
        try:
            claims = id_token_claims(self._endpoint.exchange(code, flow.code_verifier, self._redirect_uri)["id_token"])
            validate_claims(claims, self._config.client_id, flow.nonce, self._clock())
            sub, email = claims["sub"], claims["email"]
            if not isinstance(sub, str) or not sub or not isinstance(email, str) or not email.strip():
                raise ValueError("bad sub or email")
            if len(email) > _MAX_EMAIL:
                return fail("claims_email")
            name = claims.get("name")
        except GoogleError as exc:
            return fail(str(exc))
        except (KeyError, ValueError, TypeError, AttributeError, OSError, http.client.HTTPException) as exc:
            return fail(f"claims_{type(exc).__name__}")
        email = normalise_email(email)
        if flow.intent == "login":
            return self._login(flow, sub, email, name if isinstance(name, str) else None, ip, user_agent, fail)
        assert current is not None  # checked above for link and reauth
        return self._link_or_reauth(flow, sub, current, ip, user_agent, fail)

    def _link_or_reauth(self, flow: LoginFlow, sub: str, current: Principal, ip: str, user_agent: str,
                        fail) -> GoogleOutcome:
        owner = self._stores.users.by_identity("google", sub)
        if flow.intent == "link":
            if owner is not None and owner.id != current.user_id:
                return fail("sub_in_use")
            if owner is None:
                if any(i.provider == "google" for i in self._stores.users.identities(current.user_id)):
                    return fail("already_linked", "This account is already connected to a Google account.")
                try:
                    self._stores.users.add_identity(Identity("google", sub, current.user_id))
                except AuthError:
                    return fail("link_refused")
            self._audit.record("google_linked", "ok", user_id=current.user_id, ip=ip, user_agent=user_agent)
            return GoogleOutcome(None, flow.next_path, None)
        if owner is None or owner.id != current.user_id:
            return fail("sub_mismatch")
        self._sessions.mark_reauth_hash(current.session_hash, REAUTH_SECONDS)
        self._audit.record("google_reauth", "ok", user_id=current.user_id, ip=ip, user_agent=user_agent)
        return GoogleOutcome(None, flow.next_path, None)

    def _login(self, flow: LoginFlow, sub: str, email: str, name: str | None, ip: str, user_agent: str,
               fail) -> GoogleOutcome:
        users = self._stores.users
        user = users.by_identity("google", sub)
        created = user is None
        if user is None:
            if users.by_email(email) is not None:
                return fail("email_exists", EMAIL_EXISTS)
            display = (name or "").strip()[:_NAME_LIMIT] or email.split("@")[0]
            admin = self._stores.settings.get("admin_email_claim") == email
            try:
                user = self._registration.create_user(email, display, lambda uid: Identity("google", sub, uid),
                                                      admin=admin, bypass_policy=admin)
            except EmailTaken:
                return fail("email_exists", EMAIL_EXISTS)
            except AuthError as exc:  # registration closed or cap reached
                return fail("registration_closed", str(exc))
            if admin:
                self._stores.settings.set("admin_email_claim", "")
        elif user.status != "active":
            return fail("locked")
        now = self._clock()
        users.record_login(user.id, now)
        token, _ = self._sessions.start(user.id, ip, user_agent)
        self._audit.record("google_login", "ok", user_id=user.id, ip=ip, user_agent=user_agent)
        if created:
            self._registration.notify_created(user)
        return GoogleOutcome(token, flow.next_path, None)
