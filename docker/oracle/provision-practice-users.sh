#!/usr/bin/env bash
# Create or update the two accounts behind the learners' private practice schemas, in the PDB:
#
#   OLL_PROVISIONER   creates, sizes and drops the practice schemas (OLL_U...) and their profile
#   OLL_GATEWAY       CREATE SESSION only; the app connects through it as a learner's schema
#                     (proxy authentication), so learners never have a password
#
# Runs on every database start (see startup/), so it is idempotent: it also upgrades a database
# that was created before accounts existed, and a changed password secret takes effect after a
# restart. Passwords go to SQL*Plus on stdin, never on the command line.
set -Euo pipefail

readonly provisioner_secret="${STUDY_PROVISIONER_PASSWORD_FILE:-/run/secrets/provisioner_password}"
readonly gateway_secret="${STUDY_GATEWAY_PASSWORD_FILE:-/run/secrets/gateway_password}"
readonly provisioner="${STUDY_PROVISIONER_USER:-oll_provisioner}"
readonly gateway="${STUDY_GATEWAY_USER:-oll_gateway}"
readonly pdb="${ORACLE_PDB:?ORACLE_PDB is not set}"
# On Oracle 23ai (docker/23ai/02-practice-users.sh sets PRACTICE_23AI=1) learners also get SQL domains
# and procedures, so the provisioner must be able to hand those on.
extra_grants=""
[[ ${PRACTICE_23AI:-} == 1 ]] && extra_grants=", CREATE DOMAIN, CREATE PROCEDURE"
readonly extra_grants

log() { echo "provision-practice-users: $*"; }

read_secret() {  # file -> stdout, trailing whitespace (e.g. a CR) dropped
  local value
  value="$(<"$1")"
  printf '%s' "${value%"${value##*[![:space:]]}"}"
}

for file in "$provisioner_secret" "$gateway_secret"; do
  if [[ ! -r $file ]]; then
    log "no readable password file at $file; skipping (private practice schemas stay off)"
    exit 1
  fi
done
provisioner_password="$(read_secret "$provisioner_secret")"
gateway_password="$(read_secret "$gateway_secret")"

for name in "$provisioner" "$gateway"; do
  if [[ ! $name =~ ^[A-Za-z][A-Za-z0-9_]{0,29}$ ]]; then log "invalid user name: $name"; exit 1; fi
done
for password in "$provisioner_password" "$gateway_password"; do
  if [[ -z $password || $password == *[\"\'\&]* ]]; then
    log "the passwords must be non-empty and must not contain quotes or &"; exit 1
  fi
done

"${ORACLE_HOME}/bin/sqlplus" -s -L / as sysdba <<SQL
WHENEVER SQLERROR EXIT FAILURE
SET FEEDBACK OFF VERIFY OFF ECHO OFF DEFINE OFF
ALTER SESSION SET CONTAINER = ${pdb};
DECLARE
  PROCEDURE ensure_user(name VARCHAR2, pwd VARCHAR2) IS
    found PLS_INTEGER;
  BEGIN
    SELECT COUNT(*) INTO found FROM dba_users WHERE username = UPPER(name);
    IF found = 0 THEN
      EXECUTE IMMEDIATE 'CREATE USER ' || name || ' IDENTIFIED BY "' || pwd || '" PROFILE orastudy_profile';
    ELSE
      EXECUTE IMMEDIATE 'ALTER USER ' || name || ' IDENTIFIED BY "' || pwd || '" ACCOUNT UNLOCK PROFILE orastudy_profile';
    END IF;
  END;
BEGIN
  -- orastudy_profile (no password expiry) is made by provision-study-user.sh, which runs first;
  -- create it here too so the order of the scripts does not matter.
  DECLARE
    found PLS_INTEGER;
  BEGIN
    SELECT COUNT(*) INTO found FROM dba_profiles WHERE profile = 'ORASTUDY_PROFILE';
    IF found = 0 THEN
      EXECUTE IMMEDIATE 'CREATE PROFILE orastudy_profile LIMIT PASSWORD_LIFE_TIME UNLIMITED';
    END IF;
  END;
  ensure_user('${provisioner}', '${provisioner_password}');
  ensure_user('${gateway}', '${gateway_password}');
END;
/
GRANT CREATE SESSION, CREATE USER, ALTER USER, DROP USER, CREATE PROFILE, ALTER PROFILE,
      UNLIMITED TABLESPACE TO ${provisioner};
GRANT CREATE SESSION, CREATE TABLE, CREATE VIEW, CREATE SEQUENCE, CREATE SYNONYM${extra_grants}
      TO ${provisioner} WITH ADMIN OPTION;
GRANT SELECT ON sys.dba_segments TO ${provisioner};
GRANT CREATE SESSION TO ${gateway};
EXIT
SQL
status=$?
if (( status == 0 )); then log "users ${provisioner^^} and ${gateway^^} are ready in ${pdb}"; else log "failed (status $status)"; fi
exit "$status"
