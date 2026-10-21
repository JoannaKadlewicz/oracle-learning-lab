# Multi-user accounts, login and private practice schemas

Date: 2026-10-20
Status: design, approved in conversation, not yet planned

## Why

Oracle Learning Lab is a single-person app today. One progress file, one set of notes and one
shared Oracle practice schema (ORASTUDY) sit behind an optional HTTP basic-auth pop-up with one
shared password. The owner wants to open it to **anyone on the internet**. Right now that means
2-3 people, but sign-up is open. Each person gets their own account, their own progress and their
own practice database, and nobody can see or break anyone else's.

What success looks like:

- A visitor who is not logged in only ever sees a login page.
- They can register with email + password, or with one click on "Sign in with Google".
- Once in, the app looks and works as it does today, but everything is theirs alone: progress,
  settings, mistakes, mock exams, SQL history, saved notes, and the practice tables they run SQL
  against.
- The owner has a small admin page to see who signed up and to help or remove people.
- None of it is a soft target: the security choices below are what a SOC reviewer would expect
  of a public site that executes user-supplied SQL.

## Goals

1. **Mandatory authentication.** Every page and every API call except a short public list
   (below) needs a logged-in session.
2. **Two ways to register and log in:** email + password, and Google (OAuth 2.0 / OpenID Connect).
3. **Per-user state.** The `state` document (attempts, cards, labs, settings, mocks, SQL history)
   and personal notes are stored per user. Two users using the app at the same time never see
   each other's data, and concurrent requests from one user stay consistent, as they do today.
4. **Per-user practice schema.** Each user's SQL (SQL lab, flashcard "Try it", exercises, quiz
   "try it") runs in their own Oracle schema holding their own copy of the sample tables. One
   schema per database: one on 19c, and one on 23ai when that database is configured.
5. **Admin page** inside the app for admins only.
6. **Your existing progress and notes move into the first admin account**, so nothing is lost.
7. **Security throughout**, as listed in "Security requirements".
8. **Clean design.** Small single-purpose units behind interfaces (SOLID), wired in the
   composition root (`bootstrap.py`), unit-tested with in-memory fakes, the way the code base
   already works.

## Non-goals (for now)

- **Sending email.** The owner chose "without email for now". So there is no address
  verification, no emailed password reset and no email notifications. The design must make adding
  email later a matter of adding a sender, not reworking accounts.
- **Other identity providers** (GitHub, Microsoft…), 2FA/TOTP, passkeys. The identity model must
  allow them later (see "Identities").
- **Teams, sharing or any cross-user feature.**
- **Scaling beyond one app process.** The app runs as one process on Render's free plan.
  Persistent state (sessions, throttling counters) still lives in the database, so restarts lose
  nothing.
- **CAPTCHA.** The sign-up brakes below are enough at this scale. Leave a seam for it.

## Anti-goals (would be a failure even if it "works")

- A user can read or change another user's progress, notes or schema, through the API or by
  running SQL.
- One user's SQL (DROP TABLE, commit, a runaway join) breaks or stalls the app for others.
- Passwords, session tokens, OAuth secrets or schema credentials appear in logs, in error messages
  or in the browser beyond the session cookie.
- Error messages or timing reveal whether an email is registered.
- An attacker who registers someone's email with a password can later take over that person's
  Google login (account pre-hijacking).
- The app becomes unusable on a laptop without Google credentials or an Oracle admin account (see
  "Development mode").
- A new heavy framework or dependency set. The app stays standard library + `oracledb` on the
  server and vanilla JS in the browser.

## Constraints and current state

- **Stack:** Python 3.12+, standard library `http.server` (`ThreadingHTTPServer`), own tiny
  framework in `oracle_lab/web` (`Request`, `Response`, `Router`, middleware chain, controllers
  that register routes), services in `oracle_lab/services`, composition root `bootstrap.py`.
  Front end: a vanilla-JS SPA in `resources/static` (ES modules, hash-free routing via
  `core/router.js`), with CodeMirror and marked loaded from cdnjs and fonts from Google Fonts.
- **Only runtime dependency:** `oracledb` (thin mode). Keep it that way. Password hashing uses
  `hashlib.scrypt`; Google login uses `urllib` plus the standard library (see "Google").
- **Production:** Render free plan, one Docker container, no persistent disk. Oracle is an Always
  Free Autonomous Database (19c, and optionally 23ai) reached over TLS. App data lives in a
  separate Oracle user (`STUDY_STATE_USER`, tables created by `oracle-lab init-db`).
- **Local:** the all-in-one Docker image (Oracle 19c + app; the SYS password is in
  `secrets/oracle_pwd`) or `oracle-lab serve` on a laptop against local containers. Progress
  lives in JSON files under `STUDY_DATA_DIR` when no state user is configured.
- **Today's store interfaces** are `StateStore` (`load()` / `transaction()`, with
  `JsonStateStore`, `OracleStateStore`, `MemoryStateStore`) and `PersonalNotes` (`FileNotes`,
  `OracleNotes`). Services (`StudyService`, `MockExamService`, `SqlLabService`,
  `ExerciseService`, `NotesLibrary`) are built once in `build_app` with **one** store, and
  `SqlLabService`/`ExerciseService` pick the database of the user's exam track through
  `DatabaseCatalog`.
- **Existing middleware:** `access_log`, `error_boundary`, optional `BasicAuth`
  (`STUDY_AUTH_USER`/`STUDY_AUTH_PASSWORD`), `same_origin_only` (refuses cross-origin POSTs by
  `Origin`). The server adds `X-Content-Type-Options: nosniff` and caps bodies at 2 MB.
- **The content validator** (`oracle-lab validate`) keeps running against ORASTUDY. It is a
  developer tool and is not affected.

## Decisions made with the owner

| Topic | Decision |
|---|---|
| Who can register | Anyone on the internet (open sign-up), expected 2-3 users for now |
| Login methods | Email + password registration and login; "Sign in with Google". ("Basic auth" in the request meant email + password; the browser basic-auth pop-up is removed) |
| SQL isolation | Private Oracle schema per user, created with an Oracle admin account the owner provides |
| Email | None for now |
| Admin | A small admin page inside the app |
| Look | Match the current app style (index-card look, tokens in `css/tokens.css`, light and dark themes, works on phones and large screens) |
| 23ai learner rights | Same as today's 23ai ORASTUDY minus the role: no `DB_DEVELOPER_ROLE` (it brings `CREATE JOB`); content that queries the role is rewritten to describe it |

Everything else in this document is the designer's call, marked "(designer's call)" where it is
a real choice, so the owner can check it.

## The design

### 1. Request flow and public surface

The middleware order is outermost first:

`access_log` → `error_boundary` → `security_headers` → `client_ip` → `authenticate` → `csrf` →
router.

- **`authenticate`** resolves the session cookie to a `Principal` (user id, email, role, session
  id, CSRF token) and attaches it to the request. `Request` stays frozen; it gains an optional
  `principal` field filled with `dataclasses.replace`.
- **Public paths** (no session needed):
  - `GET /login`, `GET /register`, `GET /reset` (pages)
  - `POST /api/auth/login`, `POST /api/auth/register`, `POST /api/auth/reset`
  - `GET /auth/google/start`, `GET /auth/google/callback`
  - `GET /healthz`
  - the static assets those pages need: `/css/*`, `/js/auth/*`, fonts and favicons

  Everything else is private.
- **Not logged in:** a `GET` for an HTML route redirects (302) to `/login?next=<path>`. `next`
  must be a same-site relative path (`/` followed by no second `/` or `\`); anything else is
  dropped. API calls get `401 {"error": "Login required"}`, and the SPA's `api.js` sends the
  browser to `/login` on 401.
- **Logged in, but opening `/login` or `/register`:** redirect to `/`.
- **Role check:** `/admin` and `/api/admin/*` require the `admin` role. A non-admin gets 404,
  not 403, so the admin surface is not advertised.
- **Login pages:** `login.html` and `register.html` are small separate pages with their own
  minimal JS (`js/auth/*.js`). They don't load the SPA bundle, so the app code is only served to
  logged-in users. They reuse `tokens.css`/`base.css`/`components.css` and an index-card panel
  like the "Today's session" card.

### 2. Accounts and identities

- **User** (`users`): `id` (random 128-bit, URL-safe base64; never the email), `email`
  (normalised: trimmed, lower-cased; unique), `display_name`, `role` (`learner` | `admin`),
  `status` (`active` | `locked`), `created_at`, `last_login_at`, `password_changed_at`.
- **Identity** (`identities`): `(provider, subject)` unique → `user_id`.
  - Providers now: `password` (subject = user id, plus a `password_hash` column) and `google`
    (subject = Google's `sub` claim, never the email).
  - A user may have both. New providers later are just new rows.
- **Email + password registration:**
  - Email must look like an email (a pragmatic check, ≤ 254 chars).
  - Password: 12-128 characters, not equal to the email, and not on a bundled list of the
    10,000 most common leaked passwords (a text file in `resources/`). No composition rules
    (NIST SP 800-63B).
- **Password hashing:** `hashlib.scrypt` with n=2^15, r=8, p=1, 16-byte random salt, 32-byte key.
  It is stored as a self-describing string `scrypt$n$r$p$salt$hash`, so the parameters can be
  raised later. Hashes are rehashed on login when the parameters are outdated, and compared with
  `hmac.compare_digest`.
- **Login with email + password:**
  - Every failure gives the same generic message, "Email or password is incorrect".
  - When the email is unknown, a dummy scrypt still runs, so timing doesn't reveal which emails
    exist.
  - Locked accounts get the same generic error. The admin page shows the lock.
- **Registration responses:**
  - Unknown email: create the account and log in.
  - Email already registered: answer "Could not create the account. If you already have one,
    sign in instead." This message is the same whichever provider the existing account uses.
    With no email sending there is no fully enumeration-proof option, so throttling (below)
    bounds the leak. (designer's call)
- **Google sign-in for an email that already has a password account:** do **not** merge
  automatically. That is the pre-hijacking anti-goal: without email verification, someone else
  may have registered that address. Instead, show "An account with this email already exists.
  Sign in with your password, then connect Google in Settings."
  - Settings → "Connect Google" runs the Google flow while logged in and links the identity.
  - Settings can also disconnect Google, as long as a password exists, and set a password on a
    Google-only account. (designer's call)
- **Password change** (Settings): requires the current password. It revokes every other session
  of the user and issues a new session id for the current one.
- **Delete my account** (Settings): requires the password, or a fresh Google sign-in for
  Google-only accounts. That is a third Google flow intent, `reauth`, next to `login` and `link`:
  the callback must return the same `sub` as the logged-in user, and it grants a 5-minute
  "recently authenticated" mark on the session. It deletes the user, their identities, sessions, state, notes and
  practice schemas (see 6), and logs the event.

### 3. Google (OAuth 2.0 authorization code + PKCE, OpenID Connect)

- **Configuration:**
  - `STUDY_GOOGLE_CLIENT_ID` and `STUDY_GOOGLE_CLIENT_SECRET[_FILE]` (a `Secret`).
  - `STUDY_PUBLIC_URL` (e.g. `https://oracle-learning-lab.onrender.com`). The redirect URI is
    always `STUDY_PUBLIC_URL + /auth/google/callback`. It is never built from the `Host` header.
  - Without a client ID, the Google button is hidden and the endpoints return 404.
- **`/auth/google/start`:**
  - Creates a short-lived (10 min) login-flow record server-side (in the session store, keyed by
    a random id) holding `state`, `nonce`, the PKCE `code_verifier`, `next`, and the intent
    (`login` or `link` + user id).
  - Sets a `HttpOnly; Secure; SameSite=Lax` flow cookie and redirects to Google's authorization
    endpoint with `response_type=code`, `scope=openid email profile`, `code_challenge`
    (S256), `state`, `nonce` and `prompt=select_account`.
  - The endpoint URLs are constants (`accounts.google.com/o/oauth2/v2/auth`,
    `oauth2.googleapis.com/token`). There is no discovery fetch at runtime. (designer's call)
- **`/auth/google/callback`:**
  - Checks that the flow cookie and `state` match (constant-time) and that the flow is unexpired
    and single-use (deleted on first use).
  - Exchanges the code at the token endpoint with `client_secret` + `code_verifier` over TLS,
    using certificate verification and a timeout.
  - Reads the ID token's claims. Per OIDC Core 3.1.3.7, an ID token received directly from the
    token endpoint over TLS may be validated by TLS instead of signature checking. This avoids a
    JWT/crypto dependency (designer's call). The claims still checked are:
    - `iss` ∈ {`https://accounts.google.com`, `accounts.google.com`}
    - `aud` == client id
    - `exp` in the future (60 s leeway)
    - `nonce` matches
    - `email_verified` is true
  - Login intent: find the user by identity `(google, sub)`. Otherwise, if the email is unused,
    create the user (open sign-up) with role `learner`. Otherwise refuse, as in 2.
  - Link intent: link to the logged-in user. Refuse if that `sub` belongs to someone else.
- **Errors** (user cancelled, bad state, Google down) land on `/login` with a generic message.
  Details are logged without tokens.

### 4. Sessions and CSRF

- **Session token:**
  - 32 random bytes (`secrets.token_urlsafe`).
  - The cookie `oll_session` holds the token. The store keeps only its SHA-256, so a leaked
    sessions table can't be replayed.
  - Cookie attributes: `HttpOnly; Secure; SameSite=Lax; Path=/`. `Secure` is dropped only when
    `STUDY_PUBLIC_URL` is `http://localhost…`/`127.0.0.1` (development).
  - The `__Host-` prefix is used when Secure.
- **Session record:** user id, created, last seen, expires, CSRF token, user agent (truncated)
  and IP, for the admin page and the "your sessions" list.
- **Lifetime:** 7 days idle, 30 days absolute (designer's call). Last seen is updated at most
  once a minute, to limit writes. Expired sessions are purged opportunistically, plus by a
  periodic sweep.
- **Rotation and revocation:**
  - A new token is issued on every login, on password change and when Google is linked. The
    previous session is deleted (no session fixation).
  - Logout (`POST /api/auth/logout`) deletes the session server-side and expires the cookie.
  - An admin lock or delete revokes all of that user's sessions immediately.
- **CSRF:** every non-GET request to a private endpoint must carry `X-CSRF-Token` equal to the
  session's CSRF token (constant-time compare). This is on top of `SameSite=Lax` and the existing
  same-origin `Origin` check, which stays.
  - The SPA gets the token from `GET /api/auth/me` and `api.js` adds it to every call.
  - Public auth POSTs are covered by the `Origin`/`Sec-Fetch-Site` check (`same-origin`
    required when present) plus `SameSite`, against login CSRF.

### 5. Per-user state and notes

- **`UserStateStores`** replaces the single store in services: `for_user(user_id) ->
  StateStore`. It is the same `StateStore` protocol as today, so `engine`, `recording` and
  `mocks` don't change.
  - Oracle: `user_state(user_id PK, doc CLOB IS JSON, updated_at)`. A transaction locks the
    user's row (`SELECT … FOR UPDATE`), so one user's writes queue up and other users aren't
    blocked.
  - Local: SQLite (see 9).
- **`UserNotesStores`:** `for_user(user_id) -> PersonalNotes`. Oracle `user_notes(user_id, name,
  title, body, created_at)`, PK `(user_id, name)`.
- **Services:**
  - Services stop holding a store. Controllers get a small `UserContext` (principal, the user's
    `StateStore`, `PersonalNotes` and `PracticeDatabases`) built per request by a factory, and
    services take it as an argument, or are built per request from it. Either keeps services free
    of HTTP. (Left to the builder; keep it consistent across services.)
  - `NotesLibrary` keeps the built-in notes shared and makes "My notes" per user.
  - The printable readiness report (`/report`) is per user.
- **Front-end `localStorage`:** the lab draft (`lab-sql`), "commit changes" and similar keys are
  namespaced by user id, and logout clears the current user's keys. On a shared computer, one
  user's draft SQL then never shows up for the next user. The theme stays global. On the first
  login after the upgrade, existing un-namespaced keys are moved into that user's namespace once
  (designer's call), so the owner keeps their current lab draft.

### 6. Private practice schemas

- **Two Oracle accounts per database, for the app**, both configured as secrets:
  - **Provisioner** (`STUDY_PROVISIONER_USER`, `STUDY_PROVISIONER_PASSWORD[_FILE]`;
    `…_23AI` variants for the 23ai database): ADMIN on Autonomous; locally, a dedicated
    `OLL_PROVISIONER` with `CREATE USER`, `ALTER USER` (needed for `GRANT CONNECT THROUGH` and
    quotas), `DROP USER`, `CREATE PROFILE`, and each learner system privilege held
    `WITH ADMIN OPTION`, so it can grant them without `GRANT ANY PRIVILEGE`. It is used only by the provisioning service, never on a request path
    that runs user SQL.
  - **Gateway** (`STUDY_GATEWAY_USER`, `…_PASSWORD[_FILE]`): a user with only `CREATE SESSION`.
    Each learner schema is granted `CONNECT THROUGH` the gateway. The app opens learner
    sessions with **proxy authentication** (`user="gateway[OLL_U…]"`, supported by
    python-oracledb thin mode). So learner schemas have **no usable password**: they are created
    with a random 32-byte password that is immediately discarded, and they can't be logged into
    from outside. The app never stores per-user DB credentials. (designer's call)
- **Learner schema:**
  - Name: `OLL_U` + 10 random base32 chars. It carries nothing from the email.
  - Default tablespace `DATA` on Autonomous, `USERS` locally (configurable), with a quota of 50 MB
    (configurable).
  - Grants on 19c: `CREATE SESSION`, `CREATE TABLE`, `CREATE VIEW`, `CREATE SEQUENCE`,
    `CREATE SYNONYM` (what ORASTUDY has there today).
  - Grants on 23ai (decided with the owner): the 19c set plus `CREATE DOMAIN` and
    `CREATE PROCEDURE`, matching `docker/23ai/01-grants.sql`, but with the quota instead of
    `UNLIMITED TABLESPACE`.
  - No roles at all, in particular **not** `DB_DEVELOPER_ROLE`: it includes `CREATE JOB`, which
    would let a stranger start background work that outlives their request. No `ANY`
    privileges.
  - **Content follow-up:** about 11 items in `content/t13_user_access.py` and
    `content/t15_oracle_23ai.py` say they were run "as ORASTUDY, which has the role", or query
    `role_sys_privs WHERE role = 'DB_DEVELOPER_ROLE'`. A learner without the role gets an
    empty result. These items are rewritten to describe the role's contents (for example, the
    card back lists them and the sample queries `SESSION_PRIVS`), and the validator runs
    against a 23ai user with the learner grants, so this can't regress. The validator
    connection must therefore use a learner-equivalent account on 23ai.
  - Content explanations that print the schema name (for example
    `DOMAIN_NAME = 'ORASTUDY.LAB_N15_EMAIL'`) are reworded to say "your schema", because learners
    see their own `OLL_U…` name.
  - Profile `OLL_LEARNER`: `SESSIONS_PER_USER 3`, `CPU_PER_CALL 3000` (30 s),
    `LOGICAL_READS_PER_CALL 2000000`, `IDLE_TIME 15`, `CONNECT_TIME 120`. Kernel limits may be
    ignored on Autonomous, so the app-side guards below are the real line of defence; the profile
    is best-effort.
- **App-side guards on every learner session:**
  - the existing `call_timeout` (15 s)
  - the existing row limit on fetched results
  - one SQL execution at a time per user (a per-user lock; a second concurrent run gets
    "already running")
  - a small global semaphore on concurrent learner sessions (default 8), so the free database's
    session limit is never exhausted
  - `ALTER USER` stays blocked by `database/policy.py`. Statements that would affect other
    schemas are bounded by the privileges above.
- **Provisioning flow:**
  - On registration, create the learner schema on the default database and load the sample
    tables into it, by running the existing `SampleSchema` scripts through a proxy session.
    "Restore sample data" in the SQL lab does the same reset on the user's own schema.
  - The 23ai schema is created lazily, the first time the user switches to the 1Z0-171 track.
  - The mapping `practice_schemas(user_id, database_key, schema_name, created_at, status)`
    lives in the app database.
  - Provisioning failures leave the account usable, without the SQL lab. The SQL lab then shows
    "Your practice database is being prepared" with a retry, and the error is logged and shown on
    the admin page.
- **`PracticeDatabases`** (per request) replaces the shared `DatabaseCatalog` for user SQL: it
  returns a `Database` (proxy connection to the user's schema) for the user's exam track.
  `SqlLabService`, `ExerciseService` and the flashcard cleanup path use it. The shared
  `DatabaseCatalog` (ORASTUDY) remains only for `init-db`, the validator and the database
  status shown in the rail.
- **Deleting a user** drops their schemas (`DROP USER … CASCADE`) through the provisioner.
- **Cleanup of abandoned accounts:** admins see the last login. Automatic deletion is **not**
  done for now (designer's call, since there is no email to warn people). The admin page offers
  "delete accounts inactive for N days".
- **Information exposure:**
  - Learner schemas can see other schema *names* via `ALL_USERS`, which the opaque names make
    harmless.
  - A learner can `GRANT … TO PUBLIC` on their own tables (some flashcard samples do). That only
    exposes their own practice data. It is accepted and documented.

### 7. Throttling and sign-up brakes

- **Throttle store** (database-backed, so restarts don't reset it): counters keyed by
  `login:ip:<ip>`, `login:acct:<email-hash>`, `register:ip:<ip>` and `google:ip:<ip>` in a
  sliding window.
- **Login:**
  - After 5 failures per account in 15 min, further attempts for that account wait with an
    exponential delay (1, 2, 4… up to 15 min), answered `429` with `Retry-After`.
  - Per IP: 30 failures/15 min.
  - Success resets the account counter.
  - There is no permanent lock from failures (that would let anyone lock out a victim). The admin
    "lock" is a separate, deliberate action.
- **Registration:** 3 accounts per IP per hour, and a global cap `STUDY_MAX_USERS` (default 25).
  Above the cap, registration says "Registration is closed" and the admin page shows it.
  `STUDY_REGISTRATION` = `open` (default) | `closed` lets the owner shut sign-up quickly.
- **Client IP:** `X-Forwarded-For` is trusted only when `STUDY_TRUST_PROXY=1` (set in
  `render.yaml`, since Render's proxy appends the client address). Use the right-most untrusted
  hop. Otherwise use the socket address. The server must pass the socket address into `Request`
  (today it doesn't).

### 8. Admin page

- **Access:** `/admin` in the SPA (a nav item shown only to admins), backed by `/api/admin/*`,
  which require role `admin` + CSRF.
- **Users table:** email, sign-in methods, role, status, created, last login, sessions count,
  and practice schema status/size (from `DBA_SEGMENTS`/`USER_TS_QUOTAS` through the
  provisioner; best-effort).
- **Actions** (each confirmed, each written to the audit log with the acting admin):
  - **Create a one-time password-reset link:** 32-byte token, stored hashed, valid 24 h, single
    use. It is shown once for the admin to copy and send themselves, and opens `/reset?token=…`
    to set a new password. Using it revokes all the user's sessions.
  - **Lock / unlock:** lock revokes sessions and refuses login with the generic message.
  - **Make admin / remove admin:** an admin cannot remove their own admin role or lock or delete
    themselves.
  - **Delete account** (as in 2).
  - **Recreate practice schema:** drops and re-provisions it, for a user who broke theirs beyond
    "Restore sample data".
- **Settings:** registration open/closed and the max-users cap. Environment variables give the
  defaults; changes are stored in the app database.
- **Security events:** the latest 200 audit events, filterable by type and user.

### 9. Storage back ends

Every repository is a `Protocol` with two implementations that share one SQL-ish design:

| Repository | Oracle (production, `STUDY_STATE_USER`) | Local (no state user) |
|---|---|---|
| users, identities, sessions, login flows, reset tokens, throttle counters, audit events, practice schema mapping, app settings | tables in the state user's schema, created/migrated by `init-db` | SQLite file `STUDY_DATA_DIR/app.db` (stdlib `sqlite3`, WAL mode, one connection per thread) |
| per-user state | `user_state` | SQLite table |
| per-user notes | `user_notes` | SQLite table |

- **SQLite replaces the JSON progress file and the notes directory for local use.** This is a
  designer's call: identity data needs transactions and unique constraints, which JSON files
  don't give. An in-memory implementation of each repository is used in tests.
- **Schema migrations:** a small versioned migration list per back end
  (`app_schema_version` table). `init-db` applies the pending migrations. It replaces today's
  create-if-missing for `LAB_STATE`/`LAB_NOTES`.

### 10. Migration of today's data

- **First admin:** created at startup when there are no users and `STUDY_ADMIN_EMAIL` is set.
  - The password comes from `STUDY_ADMIN_PASSWORD[_FILE]`. Or, with no password set, the account
    is Google-only and is claimed by signing in with Google using that email; the email-match rule
    is relaxed for this one bootstrap case, because the address comes from the server owner.
  - Without `STUDY_ADMIN_EMAIL`, the first account to register becomes admin. That is fine for a
    fresh local install, but logged loudly, and Render sets `STUDY_ADMIN_EMAIL`. (designer's call)
- **Progress and notes:** the existing state (`LAB_STATE` row or `progress.json`) and notes
  (`LAB_NOTES` or the notes directory) are imported into the first admin's account, once
  (recorded in `app_settings`). The old tables/files are left in place, not deleted, and a later
  release can drop them.
- **ORASTUDY's practice data** is not migrated. The admin gets a fresh learner schema like
  everyone else.
- **The old basic auth** (`STUDY_AUTH_USER`/`STUDY_AUTH_PASSWORD`) is removed. If those variables
  are still set, startup logs a warning that they're ignored. `render.yaml` and the docs are
  updated.

### 11. Development mode

- **Without Google credentials**, only email + password is offered.
- **Without provisioner/gateway configuration**, accounts, progress and notes work as usual, but
  the SQL lab and every SQL-running feature run on the shared ORASTUDY schema **for admins
  only**. Learners see "The practice database is not set up on this server". The app never
  silently lets strangers share one schema. A startup warning says so.
- **The all-in-one Docker image** gets a provisioner (a dedicated `OLL_PROVISIONER` user created
  by the container's setup script, with the SYS password it already has) and a gateway user, so
  the local image behaves like production.

### 12. Security requirements (checklist the build must meet)

- **Authentication and sessions:**
  - all of 2-4
  - no session id in URLs
  - `Cache-Control: no-store` on all authenticated responses (already the JSON default; add it
    for HTML)
- **Security headers** on every response:
  - `Content-Security-Policy`:
    - `default-src 'self'`
    - `script-src 'self' https://cdnjs.cloudflare.com` plus the hash of the one inline
      theme script
    - `style-src 'self' 'unsafe-inline' https://fonts.googleapis.com` (inline style attributes
      are used by the SPA)
    - `font-src https://fonts.gstatic.com`
    - `img-src 'self' data:`
    - `connect-src 'self'`
    - `form-action 'self' https://accounts.google.com`
    - `frame-ancestors 'none'`
    - `base-uri 'none'`
    - `object-src 'none'`
  - `Strict-Transport-Security: max-age=31536000; includeSubDomains` when the public URL is HTTPS
  - `Referrer-Policy: same-origin`
  - `Cross-Origin-Opener-Policy: same-origin` (`same-origin-allow-popups` is not needed: Google
    uses a redirect, not a popup)
  - `Permissions-Policy` that disables camera, microphone, geolocation and similar
  - `X-Frame-Options: DENY` (old browsers)
  - `X-Content-Type-Options: nosniff` (already set)
- **CDN scripts** get Subresource Integrity (`integrity` + `crossorigin`) attributes.
- **Input validation** at every endpoint: types, lengths (email ≤ 254, password ≤ 128, display
  name ≤ 80) and the existing body cap. Error messages are generic toward clients and detailed
  in logs.
- **Secrets:** all new secrets go through `credentials.Secret` (`_FILE` first), never logged, and
  `repr`-safe. Tokens (session, CSRF, reset, OAuth state/nonce/verifier) come from `secrets`.
- **Audit log:** every authentication event carries the time, event type, user id (if known),
  IP, user agent and outcome:
  - register, login success/failure, logout
  - Google login/link/unlink
  - password change/reset
  - lock/unlock, role change, delete
  - schema provisioned/failed/recreated
  - throttling triggered

  Audit events are also written to the application log in a parseable `key=value` form, so a
  log drain/SIEM can pick them up. Events are retained for 90 days.
- **Authorization tests:** for every private endpoint, a test asserts 401 when logged out, and,
  where it applies, that user A's session cannot read or change user B's state, notes or schema
  (a table-driven test over the router). Admin endpoints are tested with a learner session
  (→ 404).
- **SQL execution** stays in the learner's schema through the proxy session. There are no
  string-built statements with user input in the provisioning code: identifiers are generated
  by the app and checked against `^OLL_U[A-Z2-7]{10}$` before use, and values are bound.

### 13. UI summary

- **`/login`:**
  - an index-card panel with email, password, "Sign in", "Sign in with Google" (when configured)
    and "Create an account"
  - errors inline, the generic messages above
  - honours `next`
- **`/register`:**
  - email, password with a live strength/length hint (the 12-character minimum and "this
    password is too common" come from the server), "Create account" and "Sign up with Google"
  - shows "Registration is closed" when it is
- **`/reset?token=`:** set a new password.
- **SPA:**
  - the rail shows the user's email/name and a "Sign out" button at the bottom
  - Settings gets an "Account" section: change password / set password, connect/disconnect
    Google, your active sessions (sign out others), delete account
  - an Admin nav item for admins
- **Style:** everything uses the existing tokens, components and the index-card visual language,
  works in light and dark, at phone width and on large screens.

## What's left to the builder

- The exact module layout under `oracle_lab/` (suggested: `auth/` for passwords, sessions,
  Google, throttling and audit; `accounts/` for repositories; `provisioning/` for schemas). It
  must keep one responsibility per module and the composition in `bootstrap.py`.
- How `UserContext` reaches services (argument vs. per-request construction), consistently.
- The SQLite/Oracle SQL details and the migration format.
- Copy wording on the new pages, within the tone of the existing app.
- The test split, as long as the authorization matrix and the security checklist are covered.
  Database-dependent tests skip when no database is reachable, as today.
