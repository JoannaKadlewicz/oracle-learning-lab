"""Composition root: the only place that knows which concrete classes make up the app."""

from __future__ import annotations

import time

from oracle_lab.config import EXAM_23AI, Settings
from oracle_lab.database.connection import DatabaseCatalog, OracleDatabase
from oracle_lab.resources import NOTES_DIR, STATIC_DIR
from oracle_lab.services import Clock
from oracle_lab.services.mock_exams import MockExamService
from oracle_lab.services.sql_lab import ExerciseService, SqlLabService
from oracle_lab.services.study import StudyService
from oracle_lab.study.notes import FileNotes, NotesLibrary, PersonalNotes
from oracle_lab.study.state import JsonStateStore, StateStore
from oracle_lab.web.application import WebApplication
from oracle_lab.web.controllers.health import HealthController
from oracle_lab.web.controllers.mock_exams import MockExamController
from oracle_lab.web.controllers.notes import NotesController
from oracle_lab.web.controllers.sql_lab import ExerciseController, SqlLabController
from oracle_lab.web.controllers.study import StudyController
from oracle_lab.web.middleware import BasicAuth, Middleware, access_log, error_boundary, same_origin_only
from oracle_lab.web.routing import Router
from oracle_lab.web.static import StaticFiles


def build_catalog(settings: Settings) -> DatabaseCatalog:
    default = OracleDatabase(settings.database, settings.call_timeout_ms)
    by_exam = {}
    if settings.database_23ai is not None:
        by_exam[EXAM_23AI] = OracleDatabase(settings.database_23ai, settings.call_timeout_ms)
    return DatabaseCatalog(default, by_exam)


def build_stores(settings: Settings) -> tuple[StateStore, PersonalNotes]:
    """Where progress and personal notes are kept: Oracle when STUDY_STATE_USER is set, files otherwise."""
    if settings.state_database is None:
        return JsonStateStore(settings.state_file), FileNotes(settings.personal_notes_dir)
    from oracle_lab.database.app_store import ConnectionPool, OracleNotes, OracleStateStore

    pool = ConnectionPool(settings.state_database, settings.call_timeout_ms)
    return OracleStateStore(pool), OracleNotes(pool)


def build_app(settings: Settings, *, catalog: DatabaseCatalog | None = None, store: StateStore | None = None,
              notes: PersonalNotes | None = None, clock: Clock = time.time) -> WebApplication:
    """The web application. `catalog`, `store`, `notes` and `clock` can be replaced, e.g. in tests."""
    catalog = catalog or build_catalog(settings)
    if store is None or notes is None:
        default_store, default_notes = build_stores(settings)
        store, notes = store or default_store, notes or default_notes

    router = Router(fallback=StaticFiles(STATIC_DIR))
    controllers = (
        HealthController(),
        StudyController(StudyService(store, clock, track_databases=catalog.has_track_databases)),
        MockExamController(MockExamService(store, clock)),
        SqlLabController(SqlLabService(store, catalog, clock)),
        ExerciseController(ExerciseService(store, catalog, clock)),
        NotesController(NotesLibrary(NOTES_DIR, notes), clock),
    )
    for controller in controllers:
        controller.register(router)

    middleware: list[Middleware] = [access_log, error_boundary]
    if settings.auth is not None:
        middleware.append(BasicAuth(settings.auth))
    middleware.append(same_origin_only)
    return WebApplication(router, middleware)
