#!/usr/bin/env bash
# Healthy when the database is open and the app answers on /healthz.
set -Euo pipefail

"${ORACLE_BASE}/${CHECK_DB_FILE}" >/dev/null 2>&1 || { echo "database not open"; exit 1; }
exec oracle-lab healthcheck --timeout 5
