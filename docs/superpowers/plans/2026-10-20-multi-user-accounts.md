# Multi-user Accounts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the single-user Oracle Learning Lab into an open-registration, multi-user app. It
gets a login page, email + password and Google sign-in, per-user progress and notes, a private
Oracle practice schema per user, and an admin page.

**Architecture:** Every request passes through new middleware (client address, security
headers, session authentication, CSRF). The middleware attaches a `Principal` to the `Request`.
Controllers turn that into a `UserContext` (the user's `StateStore`, `PersonalNotes` and
`PracticeDatabases`) and build the existing services per request from it.

Identity data lives behind small repository protocols, each with three implementations:

- in-memory, for tests
- SQLite, for local use
- Oracle, for production

Learner SQL runs in a private `OLL_U…` schema, reached through a low-privilege gateway account by
Oracle proxy authentication.

**Tech Stack:** Python 3.12 standard library (`http.server`, `sqlite3`, `hashlib.scrypt`,
`secrets`, `urllib`), `oracledb` thin mode, vanilla-JS ES modules, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-10-20-multi-user-accounts-design.md`. Section numbers
below (§n) refer to it, and executors read both.

## Global Constraints

- Runtime dependencies stay exactly `oracledb>=2.0,<4`. No new packages, server or browser
  (except SRI attributes on the existing CDN tags).
- Python ≥ 3.12. `ruff check src tests` must pass (line length 130, rules in `pyproject.toml`).
- Every secret goes through `credentials.resolve_secret` / `Secret` (`NAME_FILE` first) and is
  never logged or put in `repr`.
- Tokens (session, CSRF, reset, OAuth state/nonce/verifier, flow id) come from
  `secrets.token_urlsafe(32)`. Only `sha256` hex digests of session and reset tokens are stored.
- User ids: `secrets.token_urlsafe(16)`. Emails are stored normalised (`strip().lower()`), with
  at most 254 characters.
- Passwords: 12-128 characters, not equal to the email, and not in the bundled common-password
  list. Hashed with `hashlib.scrypt(n=2**15, r=8, p=1, dklen=32)` with a 16-byte salt, stored as
  `scrypt$32768$8$1$<salt b64>$<hash b64>`.
- Sessions: 7 days idle, 30 days absolute, `last_seen` written at most once per 60 s.
- Session cookie: `__Host-oll_session` (Secure) or `oll_session` (http localhost);
  `HttpOnly; SameSite=Lax; Path=/`.
- Generic login error text, exactly: `Email or password is incorrect.`
- Throttling:
  - login: 5 failures per account in 15 min, then a delay of `min(2 ** (n - 5), 900)` s; 30
    failures per IP in 15 min
  - registration: 3 per IP per hour, global cap `STUDY_MAX_USERS` (default 25)
- Learner schema:
  - name matches `^OLL_U[A-Z2-7]{10}$`, quota 50 MB (configurable), profile `OLL_LEARNER`
  - 19c grants: `CREATE SESSION, CREATE TABLE, CREATE VIEW, CREATE SEQUENCE, CREATE SYNONYM`
  - 23ai grants: the 19c set plus `CREATE DOMAIN, CREATE PROCEDURE`
  - no roles
- Concurrency: one SQL run at a time per user; at most 8 learner sessions app-wide.
- UI copy is English, in the tone of the existing app. New pages use `tokens.css`, `base.css`
  and `components.css`, work in light/dark, at 420 px and at ≥ 1600 px.
- Commits end with the line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Database-dependent tests take the `database` / `state_database` fixtures (or a new
  `provisioner_database` fixture, Task 15) and skip when no database is reachable.

## Review Focus

1. **A session expires while the SPA is open, so the next POST returns 401.** Expect: the
   browser goes to `/login?next=<current path>` and returns there after login. Covered by a test
   in Task 12 (`next` round trip) and the `api.js` change in Task 19.
2. **The Google callback is replayed** (back button, double click, or a stale tab). Expect: a
   generic "Sign-in did not complete" on `/login`, never a 500, and no second session. Covered by
   a test in Task 11 (`test_flow_is_single_use`).
3. **One user sends two requests at once** (an answer is saved while progress loads). Expect:
   no lost update. Covered by a test in Task 5 (`test_concurrent_transactions_do_not_lose_updates`).
4. **Provisioning fails halfway** (the user is created but loading the sample data fails).
   Expect: the record says `failed`, the account still logs in, and a retry drops the half-made
   schema and creates it cleanly. Covered by a test in Task 15 (`test_retry_after_failure_recreates`).
5. **The same email is typed differently** (`" Joanna@Gmail.com"` at sign-up, `joanna@gmail.com`
   at login). Expect: login works, and a duplicate sign-up with a different case is refused.
   Covered by a test in Task 10 (`test_email_is_normalised_everywhere`).

---

## File map

```
src/oracle_lab/
  config.py                         MODIFY  new settings (Task 2)
  bootstrap.py                      MODIFY  composition of everything new (Tasks 12, 13, 14, 16, 20)
  cli.py                            MODIFY  init-db applies migrations, provisions profile (Tasks 6, 15)
  auth/__init__.py                  CREATE
  auth/models.py                    CREATE  User, Identity, SessionRecord, LoginFlow, ResetToken, AuditEvent,
                                            PracticeSchema, Principal, LoginResult, auth errors (Task 4)
  auth/tokens.py                    CREATE  new_token, new_id, token_hash (Task 4)
  auth/passwords.py                 CREATE  hashing + policy (Task 7)
  auth/sessions.py                  CREATE  SessionManager (Task 8)
  auth/throttle.py                  CREATE  Throttle (Task 9)
  auth/audit.py                     CREATE  AuditLog (Task 9)
  auth/registration.py              CREATE  Registration (Task 10)
  auth/login.py                     CREATE  PasswordLogin (Task 10)
  auth/account_settings.py          CREATE  password change/set, reset by token, sessions list (Task 10)
  auth/google.py                    CREATE  GoogleClient, GoogleSignIn (Task 11)
  accounts/__init__.py              CREATE
  accounts/repositories.py          CREATE  repository Protocols + AppStores bundle (Task 4)
  accounts/memory.py                CREATE  in-memory implementations (Task 4)
  accounts/sqlite_store.py          CREATE  SQLite implementations + migrations (Task 5)
  accounts/oracle_store.py          CREATE  Oracle implementations + migrations (Task 6)
  accounts/deletion.py              CREATE  AccountDeletion (Task 14)
  accounts/first_admin.py           CREATE  first admin + legacy import (Task 14)
  database/app_store.py             MODIFY  keep ConnectionPool + legacy readers only (Task 6)
  provisioning/__init__.py          CREATE
  provisioning/schemas.py           CREATE  SchemaProvisioner, schema_name (Task 15)
  provisioning/proxy.py             CREATE  ProxyDatabase (Task 15)
  provisioning/practice.py          CREATE  PracticeDatabases, PracticeUnavailable (Task 16)
  provisioning/guards.py            CREATE  RunGuard (Task 16)
  services/context.py               CREATE  UserContext, UserContexts (Task 13)
  services/admin.py                 CREATE  AdminService (Task 20)
  services/sql_lab.py               MODIFY  use PracticeDatabases (Task 16)
  web/http.py                       MODIFY  Request.client, Request.principal, Response.cookies (Task 1)
  web/server.py                     MODIFY  pass socket address, write Set-Cookie (Task 1)
  web/middleware.py                 MODIFY  client_address, security_headers, Authenticate, csrf; BasicAuth removed (Tasks 1, 3, 12)
  web/cookies.py                    CREATE  CookiePolicy (Task 8)
  web/pages.py                      CREATE  /login /register /reset /admin page routes (Task 12)
  web/controllers/auth.py           CREATE  AuthController (Task 12)
  web/controllers/account.py        CREATE  AccountController (Task 12)
  web/controllers/admin.py          CREATE  AdminController (Task 20)
  web/controllers/*.py              MODIFY  take UserContexts (Task 13)
  resources/common-passwords.txt    CREATE  10,000 most common passwords (Task 7)
  resources/static/login.html, register.html, reset.html          CREATE (Task 18)
  resources/static/js/auth/form.js, login.js, register.js, reset.js CREATE (Task 18)
  resources/static/css/auth.css     CREATE  (Task 18)
  resources/static/index.html       MODIFY  SRI, account block in rail, admin nav (Tasks 3, 19, 20)
  resources/static/js/core/api.js   MODIFY  CSRF header, 401 redirect (Task 19)
  resources/static/js/core/session.js CREATE  me(), csrf, signOut (Task 19)
  resources/static/js/core/store.js MODIFY  per-user namespace + one-time move (Task 19)
  resources/static/js/views/settings.js MODIFY  Account section (Task 19)
  resources/static/js/views/admin.js CREATE  (Task 20)
  resources/static/css/admin.css    CREATE  (Task 20)
  content/t13_user_access.py, t15_oracle_23ai.py, (any "ORASTUDY." wording)  MODIFY (Task 21)
docker/                             MODIFY  provisioner + gateway users in the all-in-one image (Task 17)
render.yaml, README.md, docs/docker.md  MODIFY (Task 17)
tests/                              one test module per new unit (named in each task)
```

---

### Task 1: Request knows its client and principal; responses can set cookies

**Files:**
- Modify: `src/oracle_lab/web/http.py`, `src/oracle_lab/web/server.py`, `src/oracle_lab/web/middleware.py`
- Test: `tests/test_http.py` (new), `tests/test_web.py`

**Interfaces:**
- Produces:
  - `Request.client: str = ""` (the socket peer IP) and `Request.principal: Principal | None = None`.
    `Request` stays frozen; the middleware uses `dataclasses.replace`.
  - `Response.cookies: list[str]`, raw `Set-Cookie` values written one header each by the server.
  - `Response.redirect(location: str, status: int = 302, cookies: list[str] | None = None) -> Response`.
  - `class ClientAddress: __init__(trust_proxy: bool)`: middleware that replaces `request.client`
    with the right-most `X-Forwarded-For` entry when `trust_proxy`, and otherwise leaves the
    socket address.
- Consumes: `Principal` is only referenced by type (import under `TYPE_CHECKING` from
  `oracle_lab.auth.models`, created in Task 4; until then annotate as `object | None`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_http.py
def test_client_address_ignores_forwarded_for_unless_trusted():
    seen = []
    handler = lambda r: (seen.append(r.client), Response())[1]
    req = Request("GET", "/", {"x-forwarded-for": "6.6.6.6, 1.2.3.4"}, client="10.0.0.1")
    ClientAddress(trust_proxy=False)(req, handler)
    ClientAddress(trust_proxy=True)(req, handler)
    assert seen == ["10.0.0.1", "1.2.3.4"]

def test_redirect_and_cookies_reach_the_wire(serve_app):  # small fixture: a router with one route
    status, headers, _ = serve_app(lambda r: Response.redirect("/login", cookies=["a=1; Path=/", "b=2; Path=/"]))("/x")
    assert status == 302 and headers["Location"] == "/login"
    assert headers.get_all("Set-Cookie") == ["a=1; Path=/", "b=2; Path=/"]
```

- [ ] **Step 2: Run** `pytest tests/test_http.py -v`. Expected: FAIL (`unexpected keyword 'client'`).
- [ ] **Step 3: Implement**
  - Add the fields to `Request` and `Response`, with `Response.redirect(location, status=302, cookies=None)`.
  - In `server.py`, pass `client=self.client_address[0]`, and write `Set-Cookie` once per
    `response.cookies` entry and `Location` via `headers`.
  - Add `ClientAddress` to `middleware.py`.
  - Disable redirects in the test client (`urllib.request.build_opener` with a no-redirect
    handler) for the fixture.
- [ ] **Step 4: Run** `pytest tests/test_http.py tests/test_web.py -v`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(web): client address, principal slot, cookies and redirects on the HTTP types`

---

### Task 2: Settings for accounts, Google, practice schemas

**Files:**
- Modify: `src/oracle_lab/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces (all on `Settings`, documented in the module docstring like the existing variables):
  - `public_url: str`: `STUDY_PUBLIC_URL`, default `f"http://{host}:{port}"`, trailing `/` stripped.
    It must start with `http://` or `https://`, else `ConfigurationError`.
  - `secure_cookies: bool` (property): `public_url.startswith("https://")`.
  - `trust_proxy: bool`: `STUDY_TRUST_PROXY` in `("1", "true", "yes")`.
  - `google: GoogleConfig | None`, where
    `@dataclass(frozen=True) class GoogleConfig: client_id: str; client_secret: Secret`.
    Set only when `STUDY_GOOGLE_CLIENT_ID` is set; a missing secret is a `ConfigurationError`.
  - `admin_email: str | None` (normalised) and `admin_password: Secret | None`
    (`STUDY_ADMIN_PASSWORD[_FILE]`).
  - `registration_open: bool`: `STUDY_REGISTRATION` ∈ {`open` (default), `closed`}.
  - `max_users: int`: `STUDY_MAX_USERS`, default 25, minimum 1.
  - `practice: dict[str, PracticeTarget]`, keys `"default"` and `"23ai"`, where
    `@dataclass(frozen=True) class PracticeTarget: provisioner: DatabaseTarget; gateway: DatabaseTarget; tablespace: str; quota_mb: int`.
    - `default` is built from `STUDY_PROVISIONER_USER/_PASSWORD[_FILE]`,
      `STUDY_GATEWAY_USER/_PASSWORD[_FILE]`, `STUDY_PRACTICE_TABLESPACE` (default `USERS`),
      `STUDY_PRACTICE_QUOTA_MB` (default 50), on `STUDY_DSN`.
    - `23ai` comes from the same names with suffix `_23AI`, on `STUDY_DSN_23AI`.
    - A key is present only when both of its users are set.
  - `auth` and `BasicAuthConfig` are removed.
  - `legacy_basic_auth: bool`: true when `STUDY_AUTH_PASSWORD[_FILE]` is still set (Task 12
    logs the warning).
- The `STUDY_STATE_USER == STUDY_USER` check returns only when `practice` is empty. Shared-schema
  mode would let admin SQL drop the app tables. With practice schemas, ORASTUDY never runs user
  SQL. This makes the currently failing `test_progress_cannot_live_in_the_learning_schema` pass
  again in its updated form.

- [ ] **Step 1: Write the failing tests**

```python
def test_public_url_defaults_to_host_and_port_and_decides_cookie_security():
    s = Settings.from_env({"STUDY_PORT": "9000"})
    assert s.public_url == "http://127.0.0.1:9000" and not s.secure_cookies
    assert Settings.from_env({"STUDY_PUBLIC_URL": "https://lab.example.org/"}).public_url == "https://lab.example.org"

def test_google_needs_both_id_and_secret():
    assert Settings.from_env({}).google is None
    with pytest.raises(ConfigurationError, match="STUDY_GOOGLE_CLIENT_SECRET"):
        Settings.from_env({"STUDY_GOOGLE_CLIENT_ID": "abc"})

def test_practice_targets_need_provisioner_and_gateway():
    env = {"STUDY_PROVISIONER_USER": "admin", "STUDY_PROVISIONER_PASSWORD": "p", "STUDY_GATEWAY_USER": "oll_gateway",
           "STUDY_GATEWAY_PASSWORD": "g"}
    s = Settings.from_env(env)
    assert set(s.practice) == {"default"} and s.practice["default"].quota_mb == 50 and s.practice["default"].tablespace == "USERS"
    assert Settings.from_env({"STUDY_PROVISIONER_USER": "admin"}).practice == {}

def test_progress_cannot_live_in_the_learning_schema():
    with pytest.raises(ConfigurationError, match="STUDY_STATE_USER"):
        Settings.from_env({"STUDY_USER": "orastudy", "STUDY_STATE_USER": "ORASTUDY"})
    # allowed once learners have their own schemas
    Settings.from_env({"STUDY_USER": "orastudy", "STUDY_STATE_USER": "ORASTUDY", "STUDY_PROVISIONER_USER": "a",
                       "STUDY_PROVISIONER_PASSWORD": "p", "STUDY_GATEWAY_USER": "g", "STUDY_GATEWAY_PASSWORD": "g"})

def test_registration_and_cap():
    assert Settings.from_env({"STUDY_REGISTRATION": "closed"}).registration_open is False
    assert Settings.from_env({}).max_users == 25
```

  Delete `test_an_empty_auth_password_turns_login_off` and the other basic-auth config tests.
- [ ] **Step 2: Run** `pytest tests/test_config.py -v`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement** the fields and helpers (`_public_url`, `_google`, `_practice(env, suffix, dsn)`), following the existing `_integer` / `_state_database` style.
- [ ] **Step 4: Run** `pytest tests/test_config.py -v`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(config): settings for accounts, Google sign-in and practice schemas`

---

### Task 3: Security headers and SRI

**Files:**
- Modify: `src/oracle_lab/web/middleware.py`, `src/oracle_lab/web/static.py`, `src/oracle_lab/resources/static/index.html`
- Test: `tests/test_http.py`

**Interfaces:**
- Produces: `class SecurityHeaders: __init__(hsts: bool, inline_script_hashes: tuple[str, ...])`,
  middleware adding the §12 headers to every response. `CSP` is built from a constant template
  plus `'sha256-…'` entries for the inline scripts. `static.inline_script_hashes(html: str) -> tuple[str, ...]`
  computes the sha256-base64 of each `<script>` without `src` in a page (used for `index.html`
  and the auth pages at startup).
- `StaticFiles` responses for `.html` get `Cache-Control: no-store`.

- [ ] **Step 1: Write the failing test**

```python
def test_every_response_carries_the_security_headers():
    resp = SecurityHeaders(hsts=True, inline_script_hashes=("sha256-abc=",))(Request("GET", "/"), lambda r: Response())
    csp = resp.headers["Content-Security-Policy"]
    for part in ("default-src 'self'", "script-src 'self' https://cdnjs.cloudflare.com 'sha256-abc='",
                 "frame-ancestors 'none'", "form-action 'self' https://accounts.google.com", "object-src 'none'",
                 "base-uri 'none'", "font-src https://fonts.gstatic.com"):
        assert part in csp
    assert resp.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"
    assert resp.headers["X-Frame-Options"] == "DENY" and resp.headers["Referrer-Policy"] == "same-origin"
    assert resp.headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert "camera=()" in resp.headers["Permissions-Policy"]
    assert "Strict-Transport-Security" not in SecurityHeaders(False, ())(Request("GET", "/"), lambda r: Response()).headers

def test_inline_script_hash_matches_the_page():
    h = inline_script_hashes("<script>let a=1;</script><script src='/x.js'></script>")
    assert h == ("sha256-" + base64.b64encode(hashlib.sha256(b"let a=1;").digest()).decode(),)
```

- [ ] **Step 2: Run** `pytest tests/test_http.py -k "security or inline" -v`. Expected: FAIL.
- [ ] **Step 3: Implement**, and add `integrity="sha384-…" crossorigin="anonymous"` to each cdnjs
  `<script>` in `index.html`. Get the hashes from cdnjs's SRI values or compute them:
  `curl -s URL | openssl dgst -sha384 -binary | openssl base64 -A`.
- [ ] **Step 4: Run** the tests (PASS). Then open the app (`oracle-lab serve`) and confirm in
  the browser console that there are no CSP violations on Today, SQL lab (CodeMirror) and Notes
  (marked).
- [ ] **Step 5: Commit** `feat(web): security headers, CSP with inline hashes, SRI for CDN scripts`

---

### Task 4: Account models and repository protocols, in memory

**Files:**
- Create: `src/oracle_lab/auth/__init__.py`, `auth/models.py`, `auth/tokens.py`, `accounts/__init__.py`, `accounts/repositories.py`, `accounts/memory.py`
- Test: `tests/test_accounts_memory.py`, plus `tests/accounts_contract.py` (a reusable contract test suite)

**Interfaces (Produces, used by every later task):**

```python
# auth/models.py — frozen dataclasses
Role = Literal["learner", "admin"]; Status = Literal["active", "locked"]
User(id, email, display_name, role: Role, status: Status, created_at: float, last_login_at: float | None,
     password_changed_at: float | None)
Identity(provider: Literal["password", "google"], subject: str, user_id: str, password_hash: str | None = None)
SessionRecord(token_hash, user_id, csrf_token, created_at, last_seen_at, expires_at, ip, user_agent, reauth_until: float = 0.0)
LoginFlow(id, state, nonce, code_verifier, intent: Literal["login", "link", "reauth"], user_id: str | None, next_path: str, expires_at: float)
ResetToken(token_hash, user_id, created_by, expires_at, used_at: float | None = None)
AuditEvent(t, event, outcome: Literal["ok", "fail", "denied"], user_id: str | None, ip: str, user_agent: str, detail: dict)
PracticeSchema(user_id, database_key, schema_name, status: Literal["provisioning", "ready", "failed"], created_at, error: str | None = None)
Principal(user_id, email, role: Role, session_hash, csrf_token, reauth_until: float)
LoginResult(token: str, user: User)
class AuthError(Exception): status = 400 (message is safe to show)
  InvalidCredentials(401), RegistrationClosed(403), EmailTaken(409), WeakPassword(400, problems: list[str]),
  Throttled(429, retry_after: int), ReauthRequired(403)

# auth/tokens.py
new_token() -> str            # secrets.token_urlsafe(32)
new_id() -> str               # secrets.token_urlsafe(16)
token_hash(token: str) -> str # sha256 hex
normalise_email(email: str) -> str

# accounts/repositories.py — Protocols
UserRepository: add(user, identity) (atomic; EmailTaken on duplicate email or identity); get(user_id); by_email(email);
  by_identity(provider, subject) -> User | None; identities(user_id) -> list[Identity]; add_identity(identity);
  remove_identity(user_id, provider); update(user); set_password(user_id, password_hash, changed_at);
  delete(user_id); all() -> list[User]; count() -> int
SessionRepository: add(rec); get(token_hash); touch(token_hash, t); set_reauth(token_hash, until); delete(token_hash);
  delete_for_user(user_id, keep: str | None = None); for_user(user_id) -> list[SessionRecord]; purge(now)
FlowRepository: add(flow); take(flow_id) -> LoginFlow | None   # returns and deletes; purge(now)
ResetTokenRepository: add(tok); take(token_hash, now) -> ResetToken | None  # unused + unexpired, marks used
ThrottleRepository: record(key, t); count_since(key, since) -> int; last(key) -> float | None; clear(key); purge(before)
AuditRepository: add(event); recent(limit=200, event=None, user_id=None) -> list[AuditEvent]; purge(before)
SettingsRepository: get(key) -> str | None; set(key, value)
PracticeSchemaRepository: get(user_id, database_key); put(rec); for_user(user_id); delete_for_user(user_id); all()
UserStateStores: for_user(user_id) -> StateStore; delete(user_id)
UserNotesStores: for_user(user_id) -> PersonalNotes; delete(user_id)

@dataclass(frozen=True) class AppStores: users, sessions, flows, resets, throttle, audit, settings, schemas, states, notes

# accounts/memory.py
memory_stores() -> AppStores
```

- [ ] **Step 1: Write the failing contract tests** in `tests/accounts_contract.py`, as
  functions taking an `AppStores`, each asserting one behaviour:
  - `user_round_trip`: add, then `get` / `by_email` / `by_identity` return equal `User`s.
  - `duplicate_email_raises_email_taken`
  - `duplicate_identity_raises_email_taken`
  - `delete_removes_identities`
  - `flow_take_is_single_use`: the second `take` returns `None`.
  - `reset_take_rejects_used_and_expired`
  - `sessions_delete_for_user_keeps_one`
  - `purge_drops_expired_sessions_and_flows`
  - `throttle_counts_window`
  - `audit_recent_newest_first_and_filters`
  - `settings_round_trip`
  - `state_store_is_per_user`: a `transaction` on user A's store is not seen by user B.
  - `notes_are_per_user`

  `tests/test_accounts_memory.py` parametrizes them over `memory_stores()`.
- [ ] **Step 2: Run** `pytest tests/test_accounts_memory.py -v`. Expected: FAIL (import errors).
- [ ] **Step 3: Implement** the models, tokens, protocols and memory classes. The memory state
  store reuses `MemoryStateStore`; memory notes is a dict. One `threading.Lock` per repository.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat(accounts): account models, repository protocols and in-memory stores`

---

### Task 5: SQLite stores (local mode)

**Files:**
- Create: `src/oracle_lab/accounts/sqlite_store.py`
- Test: `tests/test_accounts_sqlite.py`

**Interfaces:**
- Produces: `sqlite_stores(path: Path) -> AppStores`. Migrations are a list of SQL scripts
  applied in order inside one transaction each, tracked in `app_schema_version(version INTEGER)`.
  Connection: `sqlite3.connect(path, isolation_level=None, check_same_thread=False)` per thread
  (`threading.local`), `PRAGMA journal_mode=WAL`, `PRAGMA foreign_keys=ON`,
  `PRAGMA busy_timeout=5000`. A state transaction uses `BEGIN IMMEDIATE`, so a user's writes
  serialize.
- Tables: `users`, `identities` (PK provider+subject, FK user ON DELETE CASCADE), `sessions`,
  `login_flows`, `reset_tokens`, `throttle(key, t)`, `audit`, `app_settings`,
  `practice_schemas` (PK user_id+database_key), `user_state(user_id PK, doc TEXT)`,
  `user_notes(user_id, name, title, body, created_at, PK(user_id, name))`. All `user_*` tables
  cascade on user delete.

- [ ] **Step 1: Write the failing tests:** parametrize the Task 4 contract over
  `sqlite_stores(tmp_path / "app.db")`, plus:

```python
def test_concurrent_transactions_do_not_lose_updates(tmp_path):
    stores = sqlite_stores(tmp_path / "app.db")
    def bump():
        for _ in range(50):
            with stores.states.for_user("u1").transaction() as s:
                s.setdefault("n", 0); s["n"] += 1
    threads = [threading.Thread(target=bump) for _ in range(4)]
    [t.start() for t in threads]; [t.join() for t in threads]
    assert stores.states.for_user("u1").load()["n"] == 200

def test_migrations_are_idempotent(tmp_path):
    sqlite_stores(tmp_path / "app.db"); sqlite_stores(tmp_path / "app.db")  # no error, version unchanged
```

- [ ] **Step 2: Run** `pytest tests/test_accounts_sqlite.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** `user_state.doc` is JSON text; a missing row loads `new_state()`.
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit** `feat(accounts): SQLite stores with migrations for local use`

---

### Task 6: Oracle stores (production)

**Files:**
- Create: `src/oracle_lab/accounts/oracle_store.py`
- Modify: `src/oracle_lab/database/app_store.py` (keep `ConnectionPool`, and turn `OracleStateStore`/`OracleNotes` into read-only legacy readers `LegacyOracleState`/`LegacyOracleNotes` for Task 14), `src/oracle_lab/cli.py` (`_init_db`)
- Test: `tests/test_accounts_oracle.py` (uses the `state_database` fixture), `tests/test_app_store.py` (adjust)

**Interfaces:**
- Produces:
  - `oracle_stores(database: Database) -> AppStores`
  - `migrate(database: Database) -> None`: versioned DDL list tracked in `app_schema_version`.
    Tables mirror Task 5, with Oracle types (`VARCHAR2`, `NUMBER`, `CLOB CHECK (doc IS JSON)`,
    FKs `ON DELETE CASCADE`).
  - `ensure_app_schema(database, timeout) -> bool` now waits, then calls `migrate`.
- The state transaction does `SELECT doc FROM user_state WHERE user_id = :u FOR UPDATE`, then
  `MERGE`, then commit. A missing row is inserted first: `INSERT … SELECT … WHERE NOT EXISTS`,
  then lock.
- `throttle` uses one row per hit with an index on `(key, t)`, purged by `purge(before)`.

- [ ] **Step 1: Write the failing tests:** run the contract suite against `oracle_stores(state_database)`
  after `migrate`, emptying all tables in a fixture. Also add `test_migrate_twice_is_a_no_op`
  and `test_user_state_rows_are_locked_per_user` (two threads on different users never wait on
  each other; on the same user they serialize, as in Task 5).
- [ ] **Step 2: Run** with `STUDY_TEST_STATE_USER` set. Expected: FAIL. Without it: SKIP.
- [ ] **Step 3: Implement.** Bind every value. Table names are constants.
- [ ] **Step 4: Run.** Expected: PASS (or SKIP without a database).
- [ ] **Step 5: Commit** `feat(accounts): Oracle stores with versioned migrations`

---

### Task 7: Password hashing and policy

**Files:**
- Create: `src/oracle_lab/auth/passwords.py`, `src/oracle_lab/resources/common-passwords.txt`
- Modify: `pyproject.toml` (`package-data` gains `resources/*.txt`), `src/oracle_lab/resources/__init__.py` (`COMMON_PASSWORDS` path)
- Test: `tests/test_passwords.py`

**Interfaces:**
- Produces:
  - `hash_password(password: str) -> str`
  - `verify_password(password: str, encoded: str) -> bool` (`hmac.compare_digest`)
  - `needs_rehash(encoded: str) -> bool`
  - `DUMMY_HASH: str` (computed once, for timing equalisation)
  - `class PasswordPolicy: __init__(common: frozenset[str]); problems(password: str, email: str) -> list[str]`
  - `load_common_passwords(path: Path) -> frozenset[str]` (lower-cased)

  The `problems` messages, exactly:
  - `"Use at least 12 characters."`
  - `"Use at most 128 characters."`
  - `"Don't use your email address as the password."`
  - `"This password is too common. Pick something less predictable."`
- The list: the SecLists `10-million-password-list-top-10000.txt` (MIT licence). Record the
  source URL and licence in a header comment line `# source: … licence: MIT`, skipped by the
  loader.

- [ ] **Step 1: Write the failing tests**

```python
def test_hash_round_trip_and_format():
    h = hash_password("correct horse battery")
    assert h.startswith("scrypt$32768$8$1$") and verify_password("correct horse battery", h)
    assert not verify_password("wrong", h) and hash_password("x" * 12) != hash_password("x" * 12)

def test_old_parameters_need_rehash():
    assert needs_rehash("scrypt$16384$8$1$AAAA$BBBB") and not needs_rehash(hash_password("abcdefghijkl"))

def test_policy():
    p = PasswordPolicy(frozenset({"passwordpassword"}))
    assert p.problems("short", "a@b.c") == ["Use at least 12 characters."]
    assert p.problems("PasswordPassword", "a@b.c") == ["This password is too common. Pick something less predictable."]
    assert p.problems("me@example.org", "me@example.org") == ["Don't use your email address as the password."]
    assert p.problems("a fine long passphrase", "a@b.c") == []
```

- [ ] **Step 2: Run** `pytest tests/test_passwords.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement**, with `maxmem=64 * 1024 * 1024` in `hashlib.scrypt`.
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit** `feat(auth): scrypt password hashing and password policy`

---

### Task 8: Sessions and cookies

**Files:**
- Create: `src/oracle_lab/auth/sessions.py`, `src/oracle_lab/web/cookies.py`
- Test: `tests/test_sessions.py`

**Interfaces:**
- Produces:
  - `class SessionManager: __init__(repo: SessionRepository, clock: Clock, idle: float = 7 * DAY, absolute: float = 30 * DAY)`
    - `start(user_id, ip, user_agent) -> tuple[str, SessionRecord]` (new token + csrf token,
      user agent truncated to 200 chars)
    - `resolve(token: str) -> SessionRecord | None`: `None` when unknown, idle-expired or past
      absolute; touches `last_seen` only if ≥ 60 s old.
    - `end(token)`
    - `end_all(user_id, keep_token: str | None = None)`
    - `mark_reauth(token: str, seconds: float = 300)`
  - `class CookiePolicy: __init__(secure: bool)`
    - `session_name` (`__Host-oll_session` | `oll_session`) and `flow_name`
      (`__Host-oll_flow` | `oll_flow`)
    - `set_session(token, max_age) -> str`, `clear_session() -> str`
    - `set_flow(flow_id) -> str` (max-age 600), `clear_flow() -> str`
    - `read(request, name) -> str | None` (parses `Cookie` with `http.cookies.SimpleCookie`)

- [ ] **Step 1: Write the failing tests**

```python
def test_session_expires_idle_and_absolute():
    t = [1000.0]; m = SessionManager(memory_stores().sessions, lambda: t[0])
    token, _ = m.start("u1", "1.2.3.4", "ua")
    t[0] += 6 * DAY; assert m.resolve(token)                 # touched
    t[0] += 6 * DAY; assert m.resolve(token)                 # idle window restarted
    t[0] = 1000 + 30 * DAY + 1; assert m.resolve(token) is None

def test_only_the_hash_is_stored():
    stores = memory_stores(); m = SessionManager(stores.sessions, lambda: 0)
    token, rec = m.start("u1", "", "")
    assert rec.token_hash == token_hash(token) and stores.sessions.get(token) is None

def test_end_all_keeps_the_current_one(): ...
def test_cookie_attributes():
    c = CookiePolicy(secure=True).set_session("abc", 3600)
    assert c.startswith("__Host-oll_session=abc;") and all(p in c for p in ("HttpOnly", "Secure", "SameSite=Lax", "Path=/", "Max-Age=3600"))
    assert "Secure" not in CookiePolicy(secure=False).set_session("abc", 1)
```

- [ ] **Step 2: Run** (FAIL). **Step 3: Implement.** **Step 4: Run** (PASS).
- [ ] **Step 5: Commit** `feat(auth): server-side sessions with idle and absolute expiry, cookie policy`

---

### Task 9: Throttling and audit log

**Files:**
- Create: `src/oracle_lab/auth/throttle.py`, `src/oracle_lab/auth/audit.py`
- Test: `tests/test_throttle.py`, `tests/test_audit.py`

**Interfaces:**
- Produces:
  - `class Throttle: __init__(repo: ThrottleRepository, clock)`
    - `check_login(email, ip)` raises `Throttled(retry_after)`
    - `login_failed(email, ip)`, `login_succeeded(email)`
    - `check_register(ip)` raises `Throttled`, `registered(ip)`
    - `check_google(ip)` (30 per IP per 15 min)

    Keys: `login:acct:<sha256(email)>`, `login:ip:<ip>`, `register:ip:<ip>`, `google:ip:<ip>`.
  - `class AuditLog: __init__(repo: AuditRepository, clock, logger=logging.getLogger("oracle_lab.audit"))`
    - `record(event: str, outcome: str, *, user_id=None, ip="", user_agent="", **detail)`.
      It also logs one line: `event=<e> outcome=<o> user=<id or -> ip=<ip> key=value…`. Values
      are `repr`-quoted when they contain spaces, and `detail` must never contain secrets; the
      callers pass only ids, emails and reasons.
    - `purge(older_than_days=90)`

- [ ] **Step 1: Write the failing tests**

```python
def test_login_delay_grows_after_five_failures():
    t = [0.0]; th = Throttle(memory_stores().throttle, lambda: t[0])
    for _ in range(5): th.check_login("a@b.c", "ip"); th.login_failed("a@b.c", "ip")
    with pytest.raises(Throttled) as e: th.check_login("a@b.c", "ip")
    assert e.value.retry_after == 1
    t[0] += 1; th.check_login("a@b.c", "ip"); th.login_failed("a@b.c", "ip")
    with pytest.raises(Throttled) as e: th.check_login("a@b.c", "ip")
    assert e.value.retry_after == 2
    th.login_succeeded("a@b.c"); th.check_login("a@b.c", "ip")   # cleared

def test_delay_is_capped_at_15_minutes(): ...   # 20 failures -> retry_after <= 900
def test_ip_limit_30_in_15_minutes(): ...
def test_three_registrations_per_ip_per_hour(): ...
def test_audit_writes_store_and_log(caplog):
    log = AuditLog(memory_stores().audit, lambda: 5.0)
    log.record("login", "fail", ip="1.2.3.4", email="a@b.c", reason="bad password")
    assert "event=login outcome=fail" in caplog.text and "password=" not in caplog.text
```

- [ ] **Step 2-4:** Run (FAIL), implement, run (PASS).
- [ ] **Step 5: Commit** `feat(auth): login and sign-up throttling, audit log`

---

### Task 10: Registration, password login, account settings

**Files:**
- Create: `src/oracle_lab/auth/registration.py`, `auth/login.py`, `auth/account_settings.py`
- Test: `tests/test_password_accounts.py`

**Interfaces:**
- Consumes: Tasks 4, 7, 8, 9. `on_user_created: Callable[[User], None]` (Task 16 hooks
  provisioning in; default no-op).
- Produces:
  - `class RegistrationPolicy: __init__(settings_repo, users, default_open: bool, default_max: int)`
    - `is_open() -> bool`, `max_users() -> int`, `set(open: bool | None, max_users: int | None)`
    - `check()` raises `RegistrationClosed("Registration is closed.")` when closed or
      `users.count() >= max_users()`
  - `class Registration: __init__(stores, policy: PasswordPolicy, registration: RegistrationPolicy, sessions: SessionManager, throttle, audit, clock, on_user_created)`
    - `with_password(email, password, ip, user_agent) -> LoginResult`
    - The first user ever gets role `admin` when no `STUDY_ADMIN_EMAIL` is configured (flag
      passed in by bootstrap: `first_user_is_admin: bool`).
    - Duplicate email → `EmailTaken("Could not create the account. If you already have one, sign in instead.")`
  - `class PasswordLogin: __init__(stores, sessions, throttle, audit, clock)`
    - `login(email, password, ip, user_agent) -> LoginResult`. Any failure (unknown email, no
      password identity, wrong password, locked) runs `verify_password(password, DUMMY_HASH)`
      when needed and raises `InvalidCredentials("Email or password is incorrect.")`. On
      success it rehashes if `needs_rehash`.
    - `logout(token)`
  - `class AccountSettings: __init__(stores, policy, sessions, audit, clock)`
    - `change_password(principal, current, new, token) -> LoginResult` (ends the other
      sessions, rotates the token)
    - `set_password(principal, new, token) -> LoginResult` (Google-only accounts; requires a
      recent reauth)
    - `reset_with_token(reset_token, new_password, ip, ua) -> None` (ends all sessions; the user
      then logs in)
    - `sessions(principal) -> list[dict]` (`created`, `last_seen`, `ip`, `user_agent`, `current: bool`)
    - `end_session(principal, token_hash)`
    - `end_other_sessions(principal)`
    - `profile(principal) -> dict` (`email`, `display_name`, `role`, `methods: ["password", "google"]`)

- [ ] **Step 1: Write the failing tests** (with `memory_stores()` and a fixed clock):

```python
def test_register_then_login(app):  # fixture wiring the classes above
    r = app.registration.with_password("me@example.org", "a fine long passphrase", "1.1.1.1", "ua")
    assert r.user.role == "learner" and app.sessions.resolve(r.token)
    assert app.login.login("me@example.org", "a fine long passphrase", "1.1.1.1", "ua").user.id == r.user.id

def test_email_is_normalised_everywhere(app):
    app.registration.with_password(" Joanna@Gmail.com", "a fine long passphrase", "ip", "ua")
    assert app.login.login("joanna@gmail.com", "a fine long passphrase", "ip", "ua")
    with pytest.raises(EmailTaken): app.registration.with_password("JOANNA@gmail.com", "another long passphrase", "ip2", "ua")

def test_failures_look_the_same(app):
    app.registration.with_password("me@example.org", "a fine long passphrase", "ip", "ua")
    msgs = set()
    for email, pw in (("me@example.org", "wrong wrong wrong"), ("nobody@example.org", "whatever whatever")):
        with pytest.raises(InvalidCredentials) as e: app.login.login(email, pw, "ip", "ua")
        msgs.add(str(e.value))
    assert msgs == {"Email or password is incorrect."}

def test_locked_user_cannot_log_in(app): ...
def test_registration_closed_and_cap(app): ...          # cap 1: second sign-up -> RegistrationClosed
def test_weak_password_lists_problems(app): ...
def test_change_password_rotates_and_ends_other_sessions(app): ...
def test_reset_token_is_single_use_and_ends_sessions(app): ...
def test_audit_records_register_login_fail_logout(app): ...
```

- [ ] **Step 2-4:** Run (FAIL), implement, run (PASS).
- [ ] **Step 5: Commit** `feat(auth): registration, password login and account settings`

---

### Task 11: Google sign-in (OIDC code flow + PKCE)

**Files:**
- Create: `src/oracle_lab/auth/google.py`
- Test: `tests/test_google.py`

**Interfaces:**
- Produces:
  - `AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"` and
    `TOKEN_URL = "https://oauth2.googleapis.com/token"`
  - `class TokenEndpoint(Protocol): exchange(code: str, code_verifier: str, redirect_uri: str) -> dict`
    (the token response JSON). The real one is `HttpTokenEndpoint(client_id, client_secret: Secret, timeout=10)`,
    which POSTs form-encoded data with `urllib.request` and the default TLS context, raising
    `GoogleError` on non-200.
  - `id_token_claims(id_token: str) -> dict`: base64url-decodes the payload segment (no
    signature check, per spec §3), raising `GoogleError` when malformed.
  - `validate_claims(claims, client_id, nonce, now) -> None`: checks `iss` ∈
    {`https://accounts.google.com`, `accounts.google.com`}, `aud == client_id` (or
    `client_id in aud` when it is a list, with `azp == client_id`), `exp + 60 > now`, `nonce`
    (constant-time), and `email_verified is True`.
  - `class GoogleSignIn: __init__(config: GoogleConfig, public_url, endpoint: TokenEndpoint, stores, sessions, registration: RegistrationPolicy, throttle, audit, clock, on_user_created)`
    - `start(intent, next_path, principal: Principal | None, ip) -> tuple[str, str]`: returns
      (authorization URL, flow id); stores a `LoginFlow` with a 600 s expiry.
      `code_challenge = b64url(sha256(verifier))`. Parameters: `response_type=code`,
      `scope=openid email profile`, `prompt=select_account`, `state`, `nonce`, `redirect_uri`,
      `code_challenge_method=S256`.
    - `finish(flow_id, state, code, ip, user_agent, current: Principal | None) -> GoogleOutcome`,
      where `GoogleOutcome(token: str | None, next_path: str, message: str | None)`.
      - `login`: as in spec §3; refuses with `"An account with this email already exists. Sign in with your password, then connect Google in Settings."`
      - `link`: links to `current`, refusing if the `sub` belongs to another user.
      - `reauth`: requires the same `sub` as `current`'s Google identity, then
        `sessions.mark_reauth`.
      - Any check failure gives `message = "Sign-in did not complete. Please try again."` and an
        audit `google … fail` with the reason.
      - Admin-email bootstrap: when `stores.settings.get("admin_email_claim") == email` and no
        user has that email, the new user is created with role `admin` and the setting is
        cleared (Task 14 sets it).

- [ ] **Step 1: Write the failing tests** with a `FakeEndpoint` returning a crafted id_token
  (`header.payload.sig`, with base64url JSON as the payload):
  - `test_start_builds_pkce_url`: the parsed query has the S256 challenge of the stored verifier,
    the right `redirect_uri`, and `state` + `nonce` equal to the stored flow.
  - `test_new_google_user_is_created_and_logged_in`
  - `test_existing_password_email_is_not_merged`: the message equals the text above, and no
    identity is added.
  - `test_flow_is_single_use`: a second `finish` with the same flow → generic message, `token is None`.
  - `test_wrong_state_nonce_aud_iss_expired_or_unverified_email_fail`, parametrized over the six
    mutations.
  - `test_link_and_reauth_need_the_logged_in_user`
  - `test_sub_not_email_identifies_the_account`: same `sub` with a changed email still logs into
    the same user.
- [ ] **Step 2-4:** Run (FAIL), implement, run (PASS).
- [ ] **Step 5: Commit** `feat(auth): Google sign-in with PKCE, state, nonce and claim checks`

---

### Task 12: Web integration: authenticate, CSRF, auth endpoints, pages

**Files:**
- Modify: `src/oracle_lab/web/middleware.py` (remove `BasicAuth`, add `Authenticate`, `csrf`, extend `same_origin_only`), `src/oracle_lab/bootstrap.py`, `src/oracle_lab/cli.py` (`_serve` log line: drop "login required/off", warn on `legacy_basic_auth`)
- Create: `src/oracle_lab/web/controllers/auth.py`, `web/controllers/account.py`, `web/pages.py`
- Test: `tests/test_web.py` (rewrite the auth part), `tests/test_auth_web.py`

**Interfaces:**
- Produces:
  - `PUBLIC_PATHS: frozenset[str]`: `/login`, `/register`, `/reset`, `/healthz`,
    `/api/auth/login`, `/api/auth/register`, `/api/auth/reset`, `/api/auth/config`,
    `/auth/google/start`, `/auth/google/callback`.
  - `PUBLIC_PREFIXES = ("/css/", "/js/auth/", "/js/core/dom.js")`. The auth pages import only
    these.
  - `class Authenticate: __init__(sessions, users, cookies, public_paths, public_prefixes)`
    - It sets `request.principal` when the session resolves to an active user.
    - Otherwise, for a private path:
      - an `/api/` path raises `HttpError(401, "Login required")`
      - a GET of an HTML route (no file suffix) returns
        `Response.redirect("/login?next=" + quote(path_with_query))`
    - `/login` and `/register` with a valid session redirect to `/`.
  - `csrf(request, call_next)`: for a non-GET with a principal, `X-CSRF-Token` must equal
    `principal.csrf_token` (`hmac.compare_digest`), else `HttpError(403, "Invalid CSRF token")`.
  - `same_origin_only` additionally refuses POSTs with `Sec-Fetch-Site` present and not
    `same-origin`.
  - `safe_next(value: str) -> str`: returns `value` if it starts with `/`, not `//` and not `/\`,
    and contains no control characters; else `/`.
  - `AuthController` routes:
    - `POST /api/auth/login {email, password}` and `POST /api/auth/register {email, password}`:
      200 `{"ok": true, "next": safe_next(next)}` + `Set-Cookie`.
    - `POST /api/auth/logout` (private): clears the cookie.
    - `GET /api/auth/me` (private): `{user: profile, csrf_token}`.
    - `GET /api/auth/config` (public): `{google: bool, registration_open: bool}`.
    - `POST /api/auth/reset {token, password}` (public)
    - `GET /auth/google/start?intent=login|link|reauth&next=` (link/reauth need a principal)
      sets the flow cookie and redirects to Google.
    - `GET /auth/google/callback?state&code` reads and clears the flow cookie, then redirects to
      `next` (with `Set-Cookie`) or to `/login?error=google`.
    - `AuthError` maps to its `status` and `{"error": message}`, with `Retry-After` for
      `Throttled`.
  - `AccountController` (private):
    - `POST /api/account/password {current, new}`
    - `POST /api/account/set-password {new}`
    - `GET /api/account/sessions`
    - `POST /api/account/sessions/end {id}` (`id` = the token hash)
    - `POST /api/account/sessions/end-others`
    - `POST /api/account/google/unlink` (refused when no password identity)
    - `POST /api/account/delete {password?}` (implemented in Task 14; registered here and
      returning 501 until then)
  - `pages.py`: GET routes for `/login`, `/register` and `/reset`, serving the HTML files of
    Task 18 (until then a minimal placeholder with a form), and `/admin` → `index.html` (the SPA
    route, role-checked in Task 20).
  - In bootstrap, the middleware order is
    `[access_log, error_boundary, SecurityHeaders(...), ClientAddress(settings.trust_proxy), Authenticate(...), csrf, same_origin_only]`,
    and `build_app` gains `stores: AppStores | None` (default: `sqlite_stores(data_dir / "app.db")`
    or `oracle_stores` when `state_database`) and `google_endpoint: TokenEndpoint | None` (for
    tests).

- [ ] **Step 1: Write the failing tests** (`tests/test_auth_web.py`, a real socket like
  `test_web.py`, with `memory_stores()`):

```python
def test_logged_out_html_redirects_to_login_with_next(serve):
    status, headers, _ = serve()("/progress?tab=2")
    assert status == 302 and headers["Location"] == "/login?next=%2Fprogress%3Ftab%3D2"

def test_logged_out_api_is_401_and_public_paths_are_open(serve):
    http = serve()
    assert http("/api/progress")[0] == 401
    assert http("/healthz")[0] == 200 and http("/login")[0] == 200 and http("/css/app.css")[0] == 200

def test_register_login_me_logout(serve):
    http = serve()
    status, headers, body = http("/api/auth/register", {"email": "a@example.org", "password": "a fine long passphrase"},
                                 headers={"Origin": ORIGIN})
    cookie = session_cookie(headers)
    me = json.loads(http("/api/auth/me", headers={"Cookie": cookie})[2])
    assert me["user"]["email"] == "a@example.org" and me["csrf_token"]
    assert http("/api/auth/logout", {}, headers={"Cookie": cookie, "X-CSRF-Token": me["csrf_token"], "Origin": ORIGIN})[0] == 200
    assert http("/api/auth/me", headers={"Cookie": cookie})[0] == 401

def test_post_without_csrf_token_is_403(serve): ...
def test_next_parameter_cannot_leave_the_site(): assert safe_next("//evil.com") == "/" and safe_next("/\\evil") == "/"
def test_login_page_redirects_home_when_logged_in(serve): ...
def test_throttled_login_returns_429_with_retry_after(serve): ...
def test_google_endpoints_404_without_configuration(serve): ...
def test_google_round_trip_with_fake_endpoint(serve): ...   # start -> callback with matching state -> session cookie
```

  Remove the basic-auth tests from `test_web.py`, and log in through a helper in the remaining
  ones.
- [ ] **Step 2-4:** Run (FAIL), implement, run `pytest -q` (all PASS except database-dependent
  skips).
- [ ] **Step 5: Commit** `feat(web): login required everywhere, CSRF, auth and account endpoints`

---

### Task 13: Per-user progress, notes and report

**Files:**
- Create: `src/oracle_lab/services/context.py`
- Modify: `web/controllers/study.py`, `mock_exams.py`, `notes.py`, `sql_lab.py`; `services/sql_lab.py` (signature only, still on the shared catalog until Task 16); `bootstrap.py`
- Test: `tests/test_isolation.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class UserContext: principal: Principal; state: StateStore; notes: PersonalNotes; practice: PracticeDatabases | None`
    (`None` until Task 16 wires it).
  - `class UserContexts: __init__(stores: AppStores, practice_factory: Callable[[Principal], PracticeDatabases] | None)`,
    with `__call__(request) -> UserContext`, which raises `HttpError(401)` without a principal.
  - Each controller takes `contexts: UserContexts` (plus what it took before, minus the store)
    and builds its service per request:
    - `StudyService(ctx.state, clock, track_databases)`
    - `MockExamService(ctx.state, clock)`
    - `NotesLibrary(NOTES_DIR, ctx.notes)`
    - `SqlLabService(ctx.state, catalog, clock)`
    - `ExerciseService(ctx.state, catalog, clock)`

  Service classes don't change in this task.

- [ ] **Step 1: Write the failing authorization-matrix test**

```python
PRIVATE = [("GET", "/api/state"), ("GET", "/api/progress"), ("GET", "/api/content"), ("GET", "/report"),
           ("POST", "/api/attempt"), ("POST", "/api/card"), ("POST", "/api/settings"), ("POST", "/api/pick"),
           ("POST", "/api/reset-progress"), ("GET", "/api/mock"), ("POST", "/api/mock/start"), ("GET", "/api/notes"),
           ("GET", "/api/note"), ("POST", "/api/notes/save"), ("POST", "/api/run"), ("POST", "/api/grade"),
           ("GET", "/api/schema"), ("POST", "/api/reset-data"), ("POST", "/api/visualize")]

@pytest.mark.parametrize("method,path", PRIVATE)
def test_every_private_endpoint_needs_a_session(serve, method, path): ...   # 401

def test_users_do_not_see_each_others_progress_or_notes(serve):
    a, b = register(serve, "a@x.org"), register(serve, "b@x.org")
    a.post("/api/settings", {"exam_date": "2027-01-01"})
    a.post("/api/notes/save", {"title": "Secret", "sql": "SELECT 1 FROM dual;"})
    assert b.get("/api/state")["settings"].get("exam_date") is None
    assert not [n for n in b.get("/api/notes") if n["path"].startswith("personal/")]
    assert b.get("/api/note?path=" + a_note_path)[0] == 404     # helper returns status on error
```

  Also add a test that the route table and `PRIVATE` stay in sync: every registered route that
  is not in `PUBLIC_PATHS` appears in `PRIVATE`, or in the admin list of Task 20.
- [ ] **Step 2-4:** Run (FAIL), implement, run (PASS).
- [ ] **Step 5: Commit** `feat: progress, mock exams, notes and report are per user`

---

### Task 14: First admin, legacy import, account deletion

**Files:**
- Create: `src/oracle_lab/accounts/first_admin.py`, `src/oracle_lab/accounts/deletion.py`
- Modify: `bootstrap.py` (run at `build_app`), `web/controllers/account.py` (delete endpoint)
- Test: `tests/test_first_admin.py`, `tests/test_deletion.py`

**Interfaces:**
- Produces:
  - `ensure_first_admin(stores, settings, clock, audit) -> None`. When `users.count() == 0` and
    `settings.admin_email` is set:
    - with an `admin_password`, create an admin with a password identity
    - otherwise store the setting `admin_email_claim = <email>` (claimed through Google, Task 11)
  - `first_user_is_admin(settings) -> bool`: `settings.admin_email is None` (passed to
    `Registration`; bootstrap logs a WARNING when it is true).
  - `import_legacy(stores, user_id, legacy_state: StateStore | None, legacy_notes: PersonalNotes | None) -> bool`:
    runs once, guarded by the setting `legacy_imported`. Copies the state document and every
    note, without deleting the sources.
  - The legacy sources are `JsonStateStore(settings.state_file)` / `FileNotes(...)` in local
    mode, and `LegacyOracleState`/`LegacyOracleNotes` (Task 6) in Oracle mode. The import runs
    for the first admin, when it is created or claimed (a hook called by `Registration` /
    `GoogleSignIn` through `on_user_created` when the role is `admin` and it is the first user).
  - `class AccountDeletion: __init__(stores, sessions, audit, drop_schemas: Callable[[str], None])`
    - `delete(user_id, actor_id)`: drops the schemas (no-op until Task 16), then deletes the
      state, notes, practice schema records, sessions, identities and the user, and records an
      audit `account_deleted`.
  - `POST /api/account/delete`: needs the password (password accounts) or `reauth_until > now`
    (Google-only), else `ReauthRequired("Confirm with Google first.")`.

- [ ] **Step 1: Write the failing tests**
  - `test_admin_created_from_settings_with_password`
  - `test_admin_email_without_password_is_claimed_by_google`: works with Task 11's fake endpoint.
  - `test_first_registered_user_is_admin_without_admin_email`
  - `test_legacy_progress_and_notes_move_once`: a second call returns `False` and nothing is
    duplicated.
  - `test_delete_removes_everything_and_ends_sessions`
  - `test_delete_needs_password_or_recent_reauth`
- [ ] **Step 2-4:** Run (FAIL), implement, run (PASS).
- [ ] **Step 5: Commit** `feat(accounts): first admin, one-time import of existing progress, account deletion`

---

### Task 15: Practice schema provisioning

**Files:**
- Create: `src/oracle_lab/provisioning/__init__.py`, `provisioning/schemas.py`, `provisioning/proxy.py`
- Modify: `tests/conftest.py` (add a `provisioner_database` fixture: `STUDY_TEST_PROVISIONER_USER/_PASSWORD[_FILE]` and `STUDY_TEST_GATEWAY_USER/_PASSWORD[_FILE]` on `STUDY_DSN`; skip when unset)
- Test: `tests/test_provisioning.py` (pure parts), `tests/test_provisioning_db.py` (uses the fixture)

**Interfaces:**
- Produces:
  - `SCHEMA_NAME = re.compile(r"^OLL_U[A-Z2-7]{10}$")`
  - `schema_name() -> str`: `"OLL_U" + base32(secrets.token_bytes(10))[:10]`
  - `checked(name) -> str` raises `ValueError` unless it matches
  - `LEARNER_GRANTS = {19: (...), 23: (... + "CREATE DOMAIN", "CREATE PROCEDURE")}` (selected by
    the database major version, `>= 23` → 23)
  - `PROFILE_DDL`: `CREATE PROFILE OLL_LEARNER LIMIT SESSIONS_PER_USER 3 CPU_PER_CALL 3000 LOGICAL_READS_PER_CALL 2000000 IDLE_TIME 15 CONNECT_TIME 120`
  - `class SchemaProvisioner: __init__(admin: Database, gateway_user: str, tablespace: str, quota_mb: int, sample_loader: Callable[[Database], dict], proxy_factory: Callable[[str], Database])`
    - `ensure_profile() -> None`: creates the profile if missing. ORA-01031 or an unsupported
      limit is logged at WARNING and ignored (Autonomous).
    - `create(name) -> None`. It runs these steps:
      1. `CREATE USER <name> IDENTIFIED BY "<random 30-char>" DEFAULT TABLESPACE <ts> QUOTA <q>M ON <ts> PROFILE OLL_LEARNER`
         (without `PROFILE` when that failed)
      2. `GRANT <grants> TO <name>`
      3. `ALTER USER <name> GRANT CONNECT THROUGH <gateway>`
      4. `sample_loader(proxy_factory(name))`

      The tablespace and gateway names are checked with `^[A-Z][A-Z0-9_$#]{0,127}$` (or
      double-quoted identifiers rejected outright).
    - `drop(name) -> None`: `DROP USER <name> CASCADE`. ORA-01918 (no such user) counts as success.
    - `size_mb(name) -> float | None`: `SELECT SUM(bytes)/1048576 FROM dba_segments WHERE owner = :o`;
      `None` on ORA-00942.
  - `class ProxyDatabase` (implements `Database`): `__init__(gateway: DatabaseTarget, schema: str, call_timeout_ms)`.
    `connect()` uses `oracledb.connect(user=f"{gateway.user}[{checked(schema)}]", password=gateway.password.reveal(), dsn=gateway.dsn)`
    plus the existing `SESSION_SETUP`. `target` is a `DatabaseTarget(schema, dsn, gateway.password)`
    for display only.
  - `cli.py` `_init_db` also calls `ensure_profile()` for each configured practice target.

- [ ] **Step 1: Write the failing tests**
  - Pure:
    - `test_schema_names_are_opaque_and_valid`: 1000 names, all match, all unique.
    - `test_checked_rejects_injection`: `checked("OLL_U1; DROP USER x")` raises.
    - `test_grants_by_version`
  - Database (skipped without the fixture):
    - `test_create_connect_through_gateway_and_drop`: after `create`, `ProxyDatabase` connects,
      `SELECT USER FROM dual` returns the name, and `employees` has rows. After `drop`, connect
      fails.
    - `test_learner_cannot_see_other_learners_tables`: two schemas; A's `SELECT * FROM <B>.employees`
      raises ORA-00942.
    - `test_retry_after_failure_recreates`: a `sample_loader` that raises once leaves the user;
      `drop` + `create` succeed.
- [ ] **Step 2-4:** Run (FAIL / SKIP), implement, run (PASS with the fixture).
- [ ] **Step 5: Commit** `feat(provisioning): private learner schemas reached through a proxy gateway`

---

### Task 16: SQL runs in the user's schema, with guards

**Files:**
- Create: `src/oracle_lab/provisioning/practice.py`, `src/oracle_lab/provisioning/guards.py`
- Modify: `services/sql_lab.py`, `web/controllers/sql_lab.py`, `services/context.py`, `bootstrap.py`, `accounts/deletion.py` (real `drop_schemas`), `auth/registration.py` and `auth/google.py` (bootstrap passes `on_user_created` = provision default schema in a background thread)
- Test: `tests/test_practice.py`

**Interfaces:**
- Produces:
  - `class PracticeUnavailable(Exception)`, with messages exactly:
    - `"Your practice database is being prepared. Try again in a minute."` (status
      `provisioning`, 503)
    - `"Your practice database could not be created. An admin has been notified."` (`failed`,
      503)
    - `"The practice database is not set up on this server."` (no practice targets and the user
      is not an admin, 503)
  - `class PracticeDatabases: __init__(principal, repo: PracticeSchemaRepository, provisioners: Mapping[str, SchemaProvisioner], gateways: Mapping[str, DatabaseTarget], shared: DatabaseCatalog, call_timeout_ms, clock)`
    - `for_exam(exam_code: str) -> Database`: maps `1Z0-171` to `"23ai"` when that target
      exists, else `"default"`.
      - With no practice targets: the shared catalog for admins, else `PracticeUnavailable`.
      - With no record yet: the default key was provisioned at sign-up; the 23ai key is
        provisioned now, synchronously, raising `PracticeUnavailable` (provisioning) if it is
        still running in another thread.
    - `provision(key) -> PracticeSchema`: sets `provisioning`, then `ready` or `failed` (with
      the `ORA-` message in `error`), and audits `schema_provisioned` / `schema_failed`.
    - `drop_all() -> None`
  - `drop_user_schemas(user_id: str, repo: PracticeSchemaRepository, provisioners: Mapping[str, SchemaProvisioner]) -> None`:
    a module function used as `AccountDeletion.drop_schemas`. Admins delete other users, so it
    must not need that user's `Principal`.
  - `class RunGuard: __init__(max_concurrent: int = 8)`
    - `run(user_id) -> ContextManager`, raising `HttpError(409, "Another statement of yours is still running.")`
      when the user already holds it, or `HttpError(503, "The practice database is busy. Try again in a moment.")`
      when the semaphore can't be acquired within 5 s.
  - `SqlLabService(state, practice: PracticeDatabases, guard: RunGuard, clock)` and
    `ExerciseService(...)` the same way. `current_database()` becomes
    `practice.for_exam(exam_code(state.load()))`. Every connect happens inside
    `guard.run(user_id)`. `reset_sample_data` resets the user's own schema.
  - `PracticeUnavailable` maps to 503 `{"error": message, "practice": "unavailable"}` in the
    controllers.

- [ ] **Step 1: Write the failing tests** with a `FakeProvisioner` that records calls and a
  `FakeDatabase`:
  - `test_learner_without_practice_targets_gets_unavailable`
  - `test_admin_falls_back_to_shared_schema`
  - `test_23ai_schema_is_created_on_first_use`
  - `test_failed_provisioning_is_reported_and_retry_recreates`
  - `test_guard_allows_one_run_per_user_and_caps_total`: two threads for the same user → 409;
    9 users with a cap of 8 → one gets 503.
  - `test_deleting_an_account_drops_its_schemas`
- [ ] **Step 2-4:** Run (FAIL), implement, run (PASS). Then, with the provisioner fixture,
  register a user through the web test client and `POST /api/run` `SELECT COUNT(*) FROM employees;`.
  Expect rows from the user's own schema.
- [ ] **Step 5: Commit** `feat: SQL lab, exercises and card samples run in the user's own schema`

---

### Task 17: Local image, Render and docs

**Files:**
- Modify: `docker/` (the all-in-one image's DB setup scripts: create `OLL_PROVISIONER` and `OLL_GATEWAY` in `ORAPDB1`), `docker-compose.yml`, `render.yaml`, `README.md`, `docs/docker.md`, `secrets/` generation script `scripts/init-secrets.sh` (new `provisioner_password`, `gateway_password`)
- Test: manual verification (below)

**Interfaces:**
- `OLL_PROVISIONER` grants:
  - `CREATE SESSION, CREATE USER, ALTER USER, DROP USER, CREATE PROFILE, SELECT ON DBA_SEGMENTS`
  - `CREATE TABLE, CREATE VIEW, CREATE SEQUENCE, CREATE SYNONYM, CREATE SESSION ... WITH ADMIN OPTION`
  - on 23ai also `CREATE DOMAIN, CREATE PROCEDURE WITH ADMIN OPTION`
  - `UNLIMITED TABLESPACE` (to grant quotas)
- `OLL_GATEWAY`: `CREATE SESSION` only.
- `render.yaml`:
  - drops `STUDY_AUTH_*`
  - adds `STUDY_PUBLIC_URL`, `STUDY_TRUST_PROXY=1`, `STUDY_ADMIN_EMAIL`,
    `STUDY_GOOGLE_CLIENT_ID`, `STUDY_GOOGLE_CLIENT_SECRET`, `STUDY_PROVISIONER_USER=ADMIN`,
    `STUDY_PROVISIONER_PASSWORD`, `STUDY_GATEWAY_USER`, `STUDY_GATEWAY_PASSWORD`,
    `STUDY_PRACTICE_TABLESPACE=DATA` (all secrets `sync: false`)
- `docs/docker.md` gains a "Accounts and Google sign-in" section:
  - creating the OAuth client in Google Cloud Console (Web application; redirect URI
    `<STUDY_PUBLIC_URL>/auth/google/callback`)
  - creating the gateway user on Autonomous (`CREATE USER oll_gateway IDENTIFIED BY …; GRANT CREATE SESSION TO oll_gateway;`)
  - the env table

- [ ] **Step 1:** Update the scripts and docs.
- [ ] **Step 2: Verify locally:**
  1. `docker compose build && docker compose up -d`
  2. Open `http://localhost:8071`. Expect a redirect to `/login`.
  3. Register two users in two browser profiles.
  4. In user A's SQL lab, run `DROP TABLE employees PURGE;`.
  5. In user B's SQL lab, run `SELECT COUNT(*) FROM employees;`. Expect rows.
  6. In A's SQL lab, run `SELECT USER FROM dual;`. Expect `OLL_U…`.
- [ ] **Step 3: Commit** `chore: provisioner and gateway users, Render settings and docs for accounts`

---

### Task 18: Login, register and reset pages

**Files:**
- Create: `resources/static/login.html`, `register.html`, `reset.html`, `js/auth/form.js`, `login.js`, `register.js`, `reset.js`, `css/auth.css`
- Modify: `css/app.css` (no change if `auth.css` is linked directly), `web/pages.py` (serve the real files)
- Test: `tests/test_auth_web.py` (page smoke), manual browser check

**Interfaces:**
- Consumes the endpoints of Task 12: `/api/auth/config`, `/api/auth/login`,
  `/api/auth/register`, `/api/auth/reset`, `/auth/google/start`.
- Produces:
  - Each page is a centred index card (reuse the `.session-card` ruling recipe from `home.css`
    as a `.auth-card` in `auth.css`, without the steps). It has the brand mark, `<h1>`, the form
    and the error area (`role="alert"`).
  - The Google button is an `<a href="/auth/google/start?intent=login&next=…">`, hidden unless
    `config.google`.
  - `/login?error=google` shows the generic Google message.
  - `/register` shows "Registration is closed." and disables the form when
    `!config.registration_open`.
  - The password field has `autocomplete="current-password"` / `"new-password"`, a show/hide
    toggle, and a hint "At least 12 characters". Server `problems` are listed under the field.
  - `form.js` exports `postForm(path, data) -> Promise<{ok, error, retryAfter}>`, adding the
    `Origin`-carrying same-origin fetch.
  - The theme follows the same `study:theme` localStorage key and inline script as
    `index.html`, so the CSP hash list includes it (Task 3 computes the hashes from all four pages).

- [ ] **Step 1: Write the failing smoke test:** each page returns 200, contains its form id
  (`login-form`, `register-form`, `reset-form`), and loads no script outside `/js/auth/` or
  `/js/core/dom.js`.
- [ ] **Step 2-4:** Run (FAIL), build the pages, run (PASS).
- [ ] **Step 5: Manual check:** with Playwright or by hand, at 420×900 and 1920×1080, light and
  dark:
  - the failed-login message
  - registering a weak password, which shows the problems
  - a successful login landing on `next`
  - no CSP errors in the console
- [ ] **Step 6: Commit** `feat(ui): login, registration and password reset pages`

---

### Task 19: SPA: session, CSRF, account settings, per-user storage

**Files:**
- Create: `resources/static/js/core/session.js`
- Modify: `js/core/api.js`, `js/core/store.js`, `js/main.js`, `js/shell.js`, `index.html` (rail account block), `js/views/settings.js`, `css/notes.css` (settings layout additions)
- Test: manual browser check; `tests/test_auth_web.py` covers the endpoints

**Interfaces:**
- Produces:
  - `session.js`:
    - `loadSession() -> Promise<{user, csrf}>` (GET `/api/auth/me`)
    - `csrfToken() -> string`
    - `currentUser() -> object`
    - `signOut() -> Promise<void>` (POST logout, then `clearUserStore()`, then `location = "/login"`)
  - `api.js`: every POST sends `X-CSRF-Token: csrfToken()`. A 401 sets
    `location = "/login?next=" + encodeURIComponent(location.pathname + location.search)` and
    throws. A 503 with `practice: "unavailable"` throws `ApiError` with the server message.
  - `store.js`: keys become `study:<userId>:<key>`, except `theme`, which stays `study:theme`.
    - `useUser(userId)` sets the namespace, and on the first call per browser moves the legacy
      keys `study:<key>` (except `theme`) into it. The move is marked by `study:migrated` =
      userId.
    - `clearUserStore()` removes the current namespace.
  - `main.js` calls `await loadSession()` and `useUser(...)` before `loadProgress()`.
  - Rail: above Settings, show the user's email (truncated, `title` = full) and a "Sign out"
    button.
  - Settings, an "Account" panel:
    - email
    - sign-in methods
    - change password (current + new), or set password for Google-only accounts (after "Confirm
      with Google" → `/auth/google/start?intent=reauth&next=/settings`)
    - connect Google (`intent=link`) or disconnect Google
    - active sessions with "Sign out" per row and "Sign out everywhere else"
    - "Delete my account", behind `confirmDialog` with `danger: true` and a password field (or
      reauth for Google-only)

- [ ] **Step 1:** Implement `session.js`, `api.js` and `store.js`, then load the app and check:
  - logging in lands on Today
  - a POST works (answer a quiz question)
  - deleting the session row server-side (or waiting) and answering again redirects to
    `/login?next=/quiz`, and logging in returns to `/quiz`
- [ ] **Step 2:** Rail account block + sign out. Check: sign out → `/login`, and the back button
  shows the login page, not cached app data (`no-store`).
- [ ] **Step 3:** Settings Account panel. Check every action against the endpoints, including
  the error messages (wrong current password, weak new password).
- [ ] **Step 4:** Check user switching in one browser: user A's lab draft is not shown to user B.
- [ ] **Step 5: Commit** `feat(ui): session-aware SPA, account settings, per-user browser storage`

---

### Task 20: Admin page

**Files:**
- Create: `src/oracle_lab/services/admin.py`, `web/controllers/admin.py`, `resources/static/js/views/admin.js`, `css/admin.css`
- Modify: `bootstrap.py`, `js/main.js` (register `admin` view), `index.html` (Admin nav item, hidden unless admin), `web/middleware.py` (admin check helper)
- Test: `tests/test_admin.py`

**Interfaces:**
- Produces:
  - `require_admin(ctx_or_principal)` raises `HttpError(404, "Not found")` for non-admins.
  - `class AdminService: __init__(stores, deletion: AccountDeletion, sessions: SessionManager, registration: RegistrationPolicy, practice_factory, audit, clock, public_url)`
    - `users() -> list[dict]`: `id`, `email`, `methods`, `role`, `status`, `created_at`,
      `last_login_at`, `sessions`, and `schemas: [{key, status, size_mb, error}]`
    - `reset_link(actor, user_id) -> str`: `f"{public_url}/reset?token={token}"`, 24 h, audited
      `reset_link_created`
    - `lock(actor, user_id)` (ends sessions), `unlock(actor, user_id)`
    - `set_role(actor, user_id, role)`
    - `delete(actor, user_id)`
    - `recreate_schema(actor, user_id, key)`
    - `delete_inactive(actor, days: int) -> int` (never deletes admins or `actor`)
    - `settings() -> dict`, `update_settings(actor, open: bool | None, max_users: int | None)`
    - `events(limit=200, event=None, user_id=None) -> list[dict]`
    - An actor acting on themselves for lock, role or delete raises
      `ValueError("You can't do that to your own account.")`.
  - `AdminController`: `GET /api/admin/users`, `GET /api/admin/events`, `GET /api/admin/settings`,
    and `POST /api/admin/{reset-link,lock,unlock,role,delete,recreate-schema,delete-inactive,settings}`.
    All need an admin principal + CSRF.
  - SPA `admin.js`: a users table (reusing `table.data`), a row actions menu with
    `confirmDialog`, a reset link shown once in a dialog with a copy button, a settings panel and
    an events table with filters.

- [ ] **Step 1: Write the failing tests**
  - `test_learner_gets_404_on_every_admin_route` (parametrized, 404 not 403)
  - `test_reset_link_works_once`
  - `test_lock_ends_sessions_and_blocks_login`
  - `test_admin_cannot_lock_or_demote_or_delete_self`
  - `test_delete_inactive_spares_admins`
  - `test_registration_settings_apply_immediately`
  - `test_every_admin_action_is_audited`
- [ ] **Step 2-4:** Run (FAIL), implement, run (PASS).
- [ ] **Step 5:** Manual check of the page at 420 px and 1920 px.
- [ ] **Step 6: Commit** `feat: admin page for users, resets, locks, schemas and security events`

---

### Task 21: Content that assumed ORASTUDY's role and name

**Files:**
- Modify: `src/oracle_lab/content/t13_user_access.py`, `src/oracle_lab/content/t15_oracle_23ai.py`, any item returned by `grep -rn "ORASTUDY\." src/oracle_lab/content/`
- Test: `oracle-lab validate` on 19c and 23ai, run as a learner-equivalent user

**Interfaces:**
- Consumes the 23ai learner grants (Task 15).
- Every item that queries `role_sys_privs`/`role_role_privs` for `DB_DEVELOPER_ROLE`, or says
  "executed … as ORASTUDY, which has the role":
  - the card or explanation text lists the role's contents in prose
  - the sample queries `SESSION_PRIVS` (what the learner actually has)
- Wording that prints `ORASTUDY.` becomes "your schema" (for example
  `DOMAIN_NAME = '<your schema>.LAB_N15_EMAIL'`).

- [ ] **Step 1:** Create a learner-equivalent validation user on 23ai: grants as `LEARNER_GRANTS[23]`
  and no role. Record the commands in `AUTHORING.md`, "Exam tracks".
- [ ] **Step 2:** Run `STUDY_DSN=localhost:1522/FREEPDB1 STUDY_USER=<that user> … oracle-lab validate`.
  Expect failures listing the role-dependent items.
- [ ] **Step 3:** Rewrite those items (front/back/explanation/try_sql) as above.
- [ ] **Step 4:** Validate again on 23ai (that user) and on 19c. Expected: `Database: 0 problem(s).`
  on both.
- [ ] **Step 5: Commit** `content: describe DB_DEVELOPER_ROLE instead of relying on it`

---

## Self-review notes

- **Spec coverage:**
  - §1 → Tasks 1, 3, 12, 18
  - §2 → Tasks 4, 7, 10, 14
  - §3 → Task 11
  - §4 → Tasks 8, 12
  - §5 → Tasks 4-6, 13, 19
  - §6 → Tasks 15, 16, 17, 21
  - §7 → Tasks 1, 9
  - §8 → Task 20
  - §9 → Tasks 4-6
  - §10 → Task 14
  - §11 → Tasks 16, 17
  - §12 → Tasks 3, 9, 12, 13 (matrix)
  - §13 → Tasks 18, 19, 20
- **Order:** each task leaves the app working. Tasks 1-11 add units without changing behaviour.
  Task 12 switches to login (the shared ORASTUDY is still used for SQL until Task 16, which is
  fine locally). Deploy to Render only after Task 17.
