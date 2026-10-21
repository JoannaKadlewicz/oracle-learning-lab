"""Composition root: the only place that knows which concrete classes make up the app."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from oracle_lab.accounts.deletion import AccountDeletion
from oracle_lab.accounts.first_admin import Sources, ensure_first_admin, first_user_is_admin, legacy_hook, retry_legacy_import
from oracle_lab.accounts.maintenance import Maintenance
from oracle_lab.accounts.repositories import AppStores
from oracle_lab.accounts.sqlite_store import sqlite_stores
from oracle_lab.auth.account_settings import AccountSettings
from oracle_lab.auth.audit import AuditLog
from oracle_lab.auth.google import GoogleSignIn, HttpTokenEndpoint, TokenEndpoint
from oracle_lab.auth.login import PasswordLogin
from oracle_lab.auth.models import Principal, User
from oracle_lab.auth.passwords import PasswordPolicy, load_common_passwords
from oracle_lab.auth.registration import Registration, RegistrationPolicy
from oracle_lab.auth.sessions import SessionManager
from oracle_lab.auth.throttle import Throttle
from oracle_lab.config import EXAM_23AI, ConfigurationError, PracticeTarget, Settings
from oracle_lab.database.connection import DatabaseCatalog, OracleDatabase
from oracle_lab.database.sample_schema import SampleSchema
from oracle_lab.provisioning.guards import RunGuard
from oracle_lab.provisioning.practice import PracticeDatabases, drop_user_schemas, provisioning_hook
from oracle_lab.provisioning.proxy import ProxyDatabase
from oracle_lab.provisioning.schemas import SchemaProvisioner
from oracle_lab.resources import COMMON_PASSWORDS, NOTES_DIR, STATIC_DIR
from oracle_lab.services import Clock
from oracle_lab.services.admin import AdminService
from oracle_lab.services.context import UserContexts
from oracle_lab.study.notes import FileNotes
from oracle_lab.study.state import JsonStateStore
from oracle_lab.web.application import WebApplication
from oracle_lab.web.controllers.account import AccountController
from oracle_lab.web.controllers.admin import AdminController
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

log = logging.getLogger(__name__)


def build_catalog(settings: Settings) -> DatabaseCatalog:
    default = OracleDatabase(settings.database, settings.call_timeout_ms)
    by_exam = {}
    if settings.database_23ai is not None:
        by_exam[EXAM_23AI] = OracleDatabase(settings.database_23ai, settings.call_timeout_ms)
    return DatabaseCatalog(default, by_exam)


def each_hook(*hooks: Callable[[User], None]) -> Callable[[User], None]:
    """One on_user_created hook running `hooks` in order, each on its own: a failing one is logged and can neither
    skip the others nor break the sign-up."""
    def on_user_created(user: User) -> None:
        for hook in hooks:
            try:
                hook(user)
            except Exception:  # noqa: BLE001
                log.exception("on_user_created hook %s failed for %s", getattr(hook, "__qualname__", hook), user.id)
    return on_user_created


PROVISIONER_CALL_TIMEOUT_MS = 120_000  # DROP USER ... CASCADE and loading the sample tables can be slow


def build_provisioner(target: PracticeTarget) -> SchemaProvisioner:
    """Creates and drops practice schemas on one target, loading the sample tables into each new one."""
    return SchemaProvisioner(OracleDatabase(target.provisioner, PROVISIONER_CALL_TIMEOUT_MS), target.gateway.user,
                             target.tablespace, target.quota_mb, sample_loader=lambda db: SampleSchema(db).reset(),
                             proxy_factory=lambda name: ProxyDatabase(target.gateway, name, PROVISIONER_CALL_TIMEOUT_MS))


def build_app_stores(settings: Settings, pool=None) -> AppStores:
    """Accounts, sessions and each user's progress and notes: in Oracle (STUDY_STATE_USER) or in data_dir/app.db."""
    if settings.state_database is None:
        return sqlite_stores(settings.data_dir / "app.db")
    from oracle_lab.accounts.oracle_store import oracle_stores
    from oracle_lab.database.app_store import ConnectionPool

    return oracle_stores(pool or ConnectionPool(settings.state_database, settings.call_timeout_ms))


def legacy_sources(settings: Settings, pool=None) -> Sources:
    """Where the single-user app kept progress and notes (files, or LAB_STATE / LAB_NOTES in Oracle mode),
    opened only when an import needs them."""
    def sources():
        if settings.state_database is None:
            return JsonStateStore(settings.state_file), FileNotes(settings.personal_notes_dir)
        from oracle_lab.database.app_store import LegacyOracleNotes, LegacyOracleState

        return LegacyOracleState(pool), LegacyOracleNotes(pool)
    return sources


def build_app(settings: Settings, *, catalog: DatabaseCatalog | None = None, stores: AppStores | None = None,
              google_endpoint: TokenEndpoint | None = None, clock: Clock = time.time,
              maintenance: bool = True) -> WebApplication:
    """The web application. `catalog`, `stores`, `google_endpoint` and `clock` can be replaced, e.g. in tests;
    `maintenance=False` skips the hourly purge thread."""
    catalog = catalog or build_catalog(settings)
    pool = None
    if settings.state_database is not None:
        from oracle_lab.database.app_store import ConnectionPool

        pool = ConnectionPool(settings.state_database, settings.call_timeout_ms)  # shared with the legacy readers
    stores = stores or build_app_stores(settings, pool)
    audit = AuditLog(stores.audit, clock)
    provisioners = {key: build_provisioner(target) for key, target in settings.practice.items()}
    gateways = {key: target.gateway for key, target in settings.practice.items()}

    def user_exists(user_id: str) -> bool:
        return stores.users.get(user_id) is not None

    def practice(principal: Principal) -> PracticeDatabases:
        return PracticeDatabases(principal, stores.schemas, provisioners, gateways, catalog, settings.call_timeout_ms,
                                 clock, audit, user_exists)
    def practice_of(user: User) -> PracticeDatabases:
        """Another user's practice databases (the admin page): same locks and checks as the user's own."""
        return practice(Principal(user.id, user.email, user.role, "", "", 0.0))
    contexts = UserContexts(stores, practice)

    cookies = CookiePolicy(settings.secure_cookies)
    sessions = SessionManager(stores.sessions, clock)
    throttle = Throttle(stores.throttle, clock)
    policy = PasswordPolicy(load_common_passwords(COMMON_PASSWORDS))
    registration_policy = RegistrationPolicy(stores.settings, stores.users, settings.registration_open,
                                             settings.max_users)
    if settings.admin_password is not None:
        problems = policy.problems(settings.admin_password.reveal(), settings.admin_email or "")
        if problems:
            raise ConfigurationError("STUDY_ADMIN_PASSWORD is too weak: " + " ".join(problems))
    sources = legacy_sources(settings, pool)
    import_legacy_data = legacy_hook(stores, sources, audit)
    start_provisioning = provisioning_hook(provisioners, stores.schemas, clock, audit, user_exists)
    on_user_created = each_hook(import_legacy_data, start_provisioning)
    if first_user_is_admin(settings):
        log.warning(
            "STUDY_ADMIN_EMAIL is not set: the first account to register becomes the admin.")
    registration = Registration(stores, policy, registration_policy, sessions, throttle, audit, clock,
                                on_user_created, first_user_is_admin=first_user_is_admin(settings))
    ensure_first_admin(stores, settings, clock, audit, on_user_created)
    retry_legacy_import(stores, sources, audit)
    deletion = AccountDeletion(stores, sessions, audit,
                               lambda user_id: drop_user_schemas(user_id, stores.schemas, provisioners))
    account = AccountSettings(stores, policy, sessions, audit, clock, throttle)
    admin = AdminService(stores, deletion, sessions, registration_policy, practice_of, audit, clock,
                         settings.public_url)
    google = None
    if settings.google is not None:
        endpoint = google_endpoint or HttpTokenEndpoint(settings.google.client_id, settings.google.client_secret)
        google = GoogleSignIn(settings.google, settings.public_url, endpoint, stores, sessions, throttle, audit,
                              clock, registration)

    if maintenance:
        Maintenance(stores, audit, clock).start()

    guard = RunGuard()
    router = Router(fallback=StaticFiles(STATIC_DIR))
    controllers = (
        HealthController(),
        Pages(STATIC_DIR),
        AuthController(PasswordLogin(stores, sessions, throttle, audit, clock), registration, registration_policy,
                       account, sessions, cookies, google),
        AccountController(account, cookies, deletion),
        AdminController(admin),
        StudyController(contexts, clock, track_databases=catalog.has_track_databases),
        MockExamController(contexts, clock),
        SqlLabController(contexts, guard, clock),
        ExerciseController(contexts, guard, clock),
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
