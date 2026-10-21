#!/usr/bin/env bash
# Runs on every start of the Oracle 23ai container, after the database is open (gvenzl/oracle-free
# runs /container-entrypoint-startdb.d on each start, unlike initdb.d, which runs only when the
# database is created). It makes the provisioner and gateway accounts for private practice schemas
# with the same idempotent script as on 19c (mounted by docker-compose.yml), so an existing 23ai
# database gets them too.
ORACLE_PDB=FREEPDB1 PRACTICE_23AI=1 /opt/provision-practice-users.sh \
  || echo "WARNING: provisioning the practice users failed; see above"
