"""A learner's practice schema, opened through the gateway account with proxy authentication."""

from __future__ import annotations

import oracledb

from oracle_lab.config import DatabaseTarget
from oracle_lab.database.connection import SESSION_SETUP
from oracle_lab.provisioning.schemas import checked


class ProxyDatabase:
    """Sessions as `schema`, authenticated as the gateway (`gateway[schema]`); no learner password exists."""

    def __init__(self, gateway: DatabaseTarget, schema: str, call_timeout_ms: int = 15000):
        self.gateway = gateway
        self.schema = checked(schema)
        self.call_timeout_ms = call_timeout_ms
        self.target = DatabaseTarget(self.schema, gateway.dsn, gateway.password)  # for display only

    def connect(self) -> oracledb.Connection:
        conn = oracledb.connect(user=f"{self.gateway.user}[{checked(self.schema)}]",
                                password=self.gateway.password.reveal(), dsn=self.gateway.dsn)
        conn.call_timeout = self.call_timeout_ms
        with conn.cursor() as cur:
            for statement in SESSION_SETUP:
                cur.execute(statement)
        return conn

    def __repr__(self) -> str:
        return f"ProxyDatabase({self.target} via {self.gateway.user})"
