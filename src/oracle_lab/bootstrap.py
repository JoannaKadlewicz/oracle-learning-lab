"""Composition root: the only place that knows which concrete classes make up the app."""

from __future__ import annotations

import logging
import time

from oracle_lab.accounts.deletion import AccountDeletion
from oracle_lab.accounts.first_admin import ensure_first_admin, first_user_is_admin, legacy_hook
from oracle_lab.accounts.repositories import AppStores
from oracle_lab.accounts.sqlite_store import sqlite_stores
from oracle_lab.auth.account_settings import AccountSettings
from oracle_lab.auth.audit import AuditLog
from oracle_lab.auth.google import GoogleSignIn, HttpTokenEndpoint, TokenEndpoint
from oracle_lab.auth.login import PasswordLogin
from oracle_lab.auth.passwords import PasswordPolicy, load_common_passwords
from oracle_lab.auth.registration import Registration, RegistrationPolicy
from oracle_lab.auth.sessions import SessionManager
from oracle_lab.auth.throttle import Throttle
from oracle_lab.config import EXAM_23AI, Settings
from oracle_lab.database.connection import DatabaseCatalog, OracleDatabase
from oracle_lab.resources import COMMON_PASSWORDS, NOTES_DIR, STATIC_DIR
from oracle_lab.services import Clock
from oracle_lab.services.context import UserContexts
from oracle_lab.study.notes import FileNotes
from oracle_lab.study.state import JsonStateStore
from oracle_lab.web.application import WebApplication
from oracle_lab.web.controllers.account import AccountController
from oracle_lab.web.controllers.auth import AuthController
from oracle_lab.web.controllers.health import HealthController
from oracle_lab.web.controllers.mock_exams import MockExamController
from oracle_lab.web.controllers.notes import NotesController
from oracle_lab.web.controllers.sql_lab import ExerciseController, SqlLabController
from oracle_lab.web.controllers.study import StudyController
from oracle_lab.web.cookies import CookiePolicy
from oracle_lab.web.middleware import (
    PUBLIC_PATHS,
    PUBLIC_PREFIXES,
    Authenticate,
    ClientAddress,
    Middleware,
    SecurityHeaders,
    access_log,
    csrf,
    error_boundary,
    same_origin_only,
)
from oracle_lab.web.pages import Pages
from oracle_lab.web.routing import Router
from oracle_lab.web.static import StaticFiles, inline_script_hashes


def build_catalog(settings: Settings) -> DatabaseCatalog:
    default = OracleDatabase(settings.database, settings.call_timeout_ms)
    by_exam = {}
    if settings.database_23ai is not None:
        by_exam[EXAM_23AI] = OracleDatabase(settings.database_23ai, settings.call_timeout_ms)
    return DatabaseCatalog(default, by_exam)


def build_app_stores(settings: Settings) -> AppStores:
    """Accounts, sessions and each user's progress and notes: in Oracle (STUDY_STATE_USER) or in data_dir/app.db."""
    if settings.state_database is None:
        return sqlite_stores(settings.data_dir / "app.db")
    from oracle_lab.accounts.oracle_store import oracle_stores
    from oracle_lab.database.app_store import ConnectionPool

    return oracle_stores(ConnectionPool(settings.state_database, settings.call_timeout_ms))


def build_legacy_sources(settings: Settings):
    """Where the single-user app kept progress and notes: files, or LAB_STATE / LAB_NOTES in Oracle mode."""
    if settings.state_database is None:
        return JsonStateStore(settings.state_file), FileNotes(settings.personal_notes_dir)
    from oracle_lab.database.app_store import ConnectionPool, LegacyOracleNotes, LegacyOracleState

    pool = ConnectionPool(settings.state_database, settings.call_timeout_ms)
    return LegacyOracleState(pool), LegacyOracleNotes(pool)


def build_app(settings: Settings, *, catalog: DatabaseCatalog | None = None, stores: AppStores | None = None,
              google_endpoint: TokenEndpoint | None = None, clock: Clock = time.time) -> WebApplication:
    """The web application. `catalog`, `stores`, `google_endpoint` and `clock` can be replaced, e.g. in tests."""
    catalog = catalog or build_catalog(settings)
    stores = stores or build_app_stores(settings)
    contexts = UserContexts(stores)

    cookies = CookiePolicy(settings.secure_cookies)
    sessions = SessionManager(stores.sessions, clock)
    throttle = Throttle(stores.throttle, clock)
    audit = AuditLog(stores.audit, clock)
    policy = PasswordPolicy(load_common_passwords(COMMON_PASSWORDS))
    registration_policy = RegistrationPolicy(stores.settings, stores.users, settings.registration_open,
                                             settings.max_users)
    legacy_state, legacy_notes = build_legacy_sources(settings)
    on_user_created = legacy_hook(stores, legacy_state, legacy_notes)
    if first_user_is_admin(settings):
        logging.getLogger(__name__).warning(
            "STUDY_ADMIN_EMAIL is not set: the first account to register becomes the admin.")
    registration = Registration(stores, policy, registration_policy, sessions, throttle, audit, clock,
                                on_user_created, first_user_is_admin=first_user_is_admin(settings))
    ensure_first_admin(stores, settings, clock, audit, on_user_created)
    deletion = AccountDeletion(stores, sessions, audit)
    account = AccountSettings(stores, policy, sessions, audit, clock, throttle)
    google = None
    if settings.google is not None:
        endpoint = google_endpoint or HttpTokenEndpoint(settings.google.client_id, settings.google.client_secret)
        google = GoogleSignIn(settings.google, settings.public_url, endpoint, stores, sessions, throttle, audit,
                              clock, registration)

    router = Router(fallback=StaticFiles(STATIC_DIR))
    controllers = (
        HealthController(),
        Pages(STATIC_DIR),
        AuthController(PasswordLogin(stores, sessions, throttle, audit, clock), registration, registration_policy,
                       account, sessions, cookies, google),
        AccountController(account, cookies, deletion),
        StudyController(contexts, clock, track_databases=catalog.has_track_databases),
        MockExamController(contexts, clock),
        SqlLabController(contexts, catalog, clock),
        ExerciseController(contexts, catalog, clock),
        NotesController(contexts, NOTES_DIR, clock),
    )
    for controller in controllers:
        controller.register(router)

    pages = (path.read_text(encoding="utf-8") for path in sorted(STATIC_DIR.glob("*.html")))
    script_hashes = tuple(h for page in pages for h in inline_script_hashes(page))
    middleware: list[Middleware] = [
        access_log, error_boundary, SecurityHeaders(settings.secure_cookies, script_hashes),
        ClientAddress(settings.trust_proxy), Authenticate(sessions, stores.users, cookies, PUBLIC_PATHS, PUBLIC_PREFIXES),
        csrf, same_origin_only,
    ]
    return WebApplication(router, middleware)
