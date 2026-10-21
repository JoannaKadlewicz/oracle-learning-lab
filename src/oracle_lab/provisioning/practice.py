"""The databases a user's SQL runs on: their own practice schemas, created on demand.

Each user gets one schema per practice target ("default", and "23ai" for the 1Z0-171 track when
configured). The default schema is started in the background at sign-up; the 23ai one is created on
first use. Without any practice target (development), admins keep the shared learning schema.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

from oracle_lab.accounts.repositories import PracticeSchemaRepository
from oracle_lab.auth.models import PracticeSchema, Principal, User
from oracle_lab.config import EXAM_23AI, DatabaseTarget
from oracle_lab.database.connection import Database, DatabaseCatalog
from oracle_lab.provisioning.proxy import ProxyDatabase
from oracle_lab.provisioning.schemas import schema_name
from oracle_lab.services import Clock

if TYPE_CHECKING:
    from oracle_lab.auth.audit import AuditLog
    from oracle_lab.provisioning.schemas import SchemaProvisioner

log = logging.getLogger(__name__)

PREPARING = "Your practice database is being prepared. Try again in a minute."
FAILED = "Your practice database could not be created. An admin has been notified."
NOT_SET_UP = "The practice database is not set up on this server."

STALE_SECONDS = 600  # a record still "provisioning" after this long was left by a crash
_ERROR_LIMIT = 500

_locks: dict[tuple[str, str], threading.Lock] = {}
_locks_guard = threading.Lock()


class PracticeUnavailable(Exception):  # noqa: N818 - name fixed by the design
    """The user's practice database cannot be used right now (503 {"error": message, "practice": "unavailable"})."""


def _lock(user_id: str, key: str) -> threading.Lock:
    """One lock per (user, practice target), so a schema is never provisioned twice at the same time."""
    with _locks_guard:
        return _locks.setdefault((user_id, key), threading.Lock())


def _first_line(exc: BaseException) -> str:
    text = str(exc).strip().splitlines()
    return (text[0] if text else type(exc).__name__)[:_ERROR_LIMIT]


def _audit(audit: AuditLog | None, event: str, outcome: str, user_id: str, **detail) -> None:
    if audit is None:
        return
    try:
        audit.record(event, outcome, user_id=user_id, **detail)
    except Exception:  # noqa: BLE001 - the schema exists (or not) either way
        log.exception("could not audit %s for %s", event, user_id)


def _provision_locked(user_id: str, key: str, repo: PracticeSchemaRepository, provisioner: SchemaProvisioner,
                      clock: Clock, audit: AuditLog | None) -> PracticeSchema:
    old = repo.get(user_id, key)
    if old is not None:
        try:
            provisioner.drop(old.schema_name)
        except Exception as exc:  # noqa: BLE001 - a half-made old schema must not block a new one
            log.warning("could not drop the old practice schema %s of %s: %s", old.schema_name, user_id, _first_line(exc))
    rec = PracticeSchema(user_id, key, schema_name(), "provisioning", clock())
    repo.put(rec)
    try:
        provisioner.create(rec.schema_name)
    except Exception as exc:  # noqa: BLE001 - recorded and audited; the user sees FAILED
        log.exception("creating the practice schema %s (%s) of %s failed", rec.schema_name, key, user_id)
        rec = PracticeSchema(user_id, key, rec.schema_name, "failed", rec.created_at, _first_line(exc))
        repo.put(rec)
        _audit(audit, "schema_failed", "fail", user_id, key=key, schema=rec.schema_name, error=rec.error)
        return rec
    rec = PracticeSchema(user_id, key, rec.schema_name, "ready", rec.created_at)
    repo.put(rec)
    _audit(audit, "schema_provisioned", "ok", user_id, key=key, schema=rec.schema_name)
    return rec


def provision_schema(user_id: str, key: str, repo: PracticeSchemaRepository, provisioner: SchemaProvisioner,
                     clock: Clock, audit: AuditLog | None = None) -> PracticeSchema:
    """(Re)creates the user's schema on target `key` under a NEW name, dropping the recorded one first (errors
    ignored). The record goes provisioning -> ready, or failed with the first line of the error."""
    with _lock(user_id, key):
        return _provision_locked(user_id, key, repo, provisioner, clock, audit)


def drop_user_schemas(user_id: str, repo: PracticeSchemaRepository,
                      provisioners: Mapping[str, SchemaProvisioner]) -> None:
    """Drops every recorded schema of the user (AccountDeletion.drop_schemas; the records are left to the caller).
    Waits for a provisioning in progress. Raises after trying all of them when one could not be dropped."""
    errors = []
    for key, provisioner in provisioners.items():
        with _lock(user_id, key):
            rec = repo.get(user_id, key)
            if rec is None:
                continue
            try:
                provisioner.drop(rec.schema_name)
            except Exception as exc:  # noqa: BLE001 - try the others first
                log.exception("could not drop the practice schema %s of %s", rec.schema_name, user_id)
                errors.append(exc)
    unknown = [rec.schema_name for rec in repo.for_user(user_id) if rec.database_key not in provisioners]
    if unknown:
        log.warning("practice schemas of %s on targets no longer configured were not dropped: %s", user_id, unknown)
    if errors:
        raise errors[0]


def provisioning_hook(provisioners: Mapping[str, SchemaProvisioner], repo: PracticeSchemaRepository, clock: Clock,
                      audit: AuditLog | None) -> Callable[[User], None]:
    """The on_user_created hook: starts the default schema in a daemon thread. Never raises."""
    provisioner = provisioners.get("default")

    def work(user_id: str) -> None:
        try:
            with _lock(user_id, "default"):
                if repo.get(user_id, "default") is None:  # e.g. already created on first use
                    _provision_locked(user_id, "default", repo, provisioner, clock, audit)
        except Exception:  # noqa: BLE001 - the first use of the SQL lab provisions it again
            log.exception("provisioning the practice schema of %s failed", user_id)

    def on_user_created(user: User) -> None:
        if provisioner is None:
            return
        try:
            threading.Thread(target=work, args=(user.id,), name=f"provision-{user.id}", daemon=True).start()
        except Exception:  # noqa: BLE001 - sign-up must complete
            log.exception("could not start provisioning for %s", user.id)

    return on_user_created


class PracticeDatabases:
    """The signed-in user's practice databases, one per exam track."""

    def __init__(self, principal: Principal, repo: PracticeSchemaRepository,
                 provisioners: Mapping[str, SchemaProvisioner], gateways: Mapping[str, DatabaseTarget],
                 shared: DatabaseCatalog, call_timeout_ms: int, clock: Clock, audit: AuditLog | None = None):
        self.principal = principal
        self.repo = repo
        self.provisioners = provisioners
        self.gateways = gateways
        self.shared = shared
        self.call_timeout_ms = call_timeout_ms
        self.clock = clock
        self.audit = audit

    @property
    def user_id(self) -> str:
        return self.principal.user_id

    def for_exam(self, exam_code: str) -> Database:
        """The database for the exam track `exam_code`; PracticeUnavailable while it cannot be used."""
        key = "23ai" if exam_code == EXAM_23AI and "23ai" in self.provisioners else "default"
        if key not in self.provisioners:
            if self.principal.role == "admin":
                return self.shared.for_exam(exam_code)
            raise PracticeUnavailable(NOT_SET_UP)
        rec = self.repo.get(self.user_id, key)
        if rec is None or self._stale(rec):
            rec = self._provision_now(key)
        if rec.status == "ready":
            return ProxyDatabase(self.gateways[key], rec.schema_name, self.call_timeout_ms)
        raise PracticeUnavailable(PREPARING if rec.status == "provisioning" else FAILED)

    def _stale(self, rec: PracticeSchema) -> bool:
        return rec.status == "provisioning" and self.clock() - rec.created_at > STALE_SECONDS

    def _provision_now(self, key: str) -> PracticeSchema:
        lock = _lock(self.user_id, key)
        if not lock.acquire(blocking=False):
            raise PracticeUnavailable(PREPARING)  # another thread (e.g. the sign-up one) is creating it
        try:
            rec = self.repo.get(self.user_id, key)
            if rec is not None and not self._stale(rec):
                return rec  # done while this request waited for the lock
            return _provision_locked(self.user_id, key, self.repo, self.provisioners[key], self.clock, self.audit)
        finally:
            lock.release()

    def provision(self, key: str) -> PracticeSchema:
        return provision_schema(self.user_id, key, self.repo, self.provisioners[key], self.clock, self.audit)

    def drop_all(self) -> None:
        drop_user_schemas(self.user_id, self.repo, self.provisioners)
        self.repo.delete_for_user(self.user_id)
