"""The Oracle engine: thin adapters over the Oracle implementation (database/, provisioning/, grading/,
analysis/), with the same arguments the app passed to them directly."""

from __future__ import annotations

from typing import Any

from oracle_lab.analysis import visualizer
from oracle_lab.config import DatabaseTarget, PracticeTarget
from oracle_lab.database.connection import Database, OracleDatabase, session
from oracle_lab.database.executor import ScriptRunner
from oracle_lab.database.query import query_rows
from oracle_lab.database.sample_schema import SampleSchema, ensure_sample_schema
from oracle_lab.database.schema import describe_schema
from oracle_lab.grading import labs
from oracle_lab.provisioning.proxy import ProxyDatabase
from oracle_lab.provisioning.schemas import SchemaProvisioner

PROVISIONER_CALL_TIMEOUT_MS = 120_000  # DROP USER ... CASCADE and loading the sample tables can be slow


class OracleEngine:
    name = "oracle"
    label = "Oracle"
    editor_mode = "text/x-plsql"

    def database(self, target: DatabaseTarget, call_timeout_ms: int) -> Database:
        return OracleDatabase(target, call_timeout_ms)

    def proxy_database(self, gateway: DatabaseTarget, schema: str, call_timeout_ms: int) -> Database:
        return ProxyDatabase(gateway, schema, call_timeout_ms)

    def provisioner(self, target: PracticeTarget, call_timeout_ms: int) -> SchemaProvisioner:
        """Creates and drops practice schemas on `target`, loading the sample tables into each new one. Its calls
        get at least PROVISIONER_CALL_TIMEOUT_MS."""
        timeout = max(call_timeout_ms, PROVISIONER_CALL_TIMEOUT_MS)
        return SchemaProvisioner(OracleDatabase(target.provisioner, timeout), target.gateway.user,
                                 target.tablespace, target.quota_mb, sample_loader=lambda db: SampleSchema(db).reset(),
                                 proxy_factory=lambda name: ProxyDatabase(target.gateway, name, timeout))

    def run_script(self, database: Database, script: str, *, keep_changes: bool = False,
                   inspect: bool = False, lang: str = "en") -> dict[str, Any]:
        return ScriptRunner(database).run(script, keep_changes=keep_changes, inspect=inspect, lang=lang)

    def run_cleanup(self, database: Database, item: dict) -> None:
        with session(database) as conn:
            labs.run_cleanup(conn, item)

    def grade(self, database: Database, lab: dict, sql: str, *, lang: str = "en") -> dict[str, Any]:
        return labs.grade(database, lab, sql, lang)

    def visualize(self, database: Database, sql: str, *, lang: str = "en") -> dict[str, Any]:
        with session(database) as conn:
            return visualizer.visualize(conn, sql, query_rows, lang)

    def describe(self, database: Database) -> dict[str, Any]:
        result = describe_schema(database)
        if result.get("ok"):
            result["database"] = {**result["database"], "product": self.label}
        return result

    def reset_sample(self, database: Database) -> dict[str, Any]:
        return SampleSchema(database).reset()

    def ensure_sample(self, database: Database, timeout: float) -> bool:
        return ensure_sample_schema(database, timeout)
