#!/usr/bin/env bash
# Runs once when the Oracle 23ai container creates its database (gvenzl/oracle-free initdb hook):
# the provisioner and gateway accounts for private practice schemas, made by the same script as on
# 19c (mounted by docker-compose.yml). For a 23ai database that already exists, run it by hand:
#   docker compose exec -e ORACLE_PDB=FREEPDB1 -e PRACTICE_23AI=1 oracle23 /opt/provision-practice-users.sh
ORACLE_PDB=FREEPDB1 PRACTICE_23AI=1 /opt/provision-practice-users.sh \
  || echo "WARNING: provisioning the practice users failed; see above"
