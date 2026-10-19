#!/usr/bin/env bash
# Create or update the learning user in the PDB, with the privileges the exercises are written for
# (the same as on the reference 19c database the content was validated on).
#
# Runs on every database start (see startup/), so it is idempotent, and a changed password
# secret takes effect after a restart. The password goes to SQL*Plus on stdin, never on the
# command line, so it does not show up in `ps`.
set -Euo pipefail

readonly secret_file="${STUDY_PASSWORD_FILE:-/run/secrets/study_db_password}"
readonly user="${STUDY_USER:-orastudy}"
readonly pdb="${ORACLE_PDB:?ORACLE_PDB is not set}"
readonly quota="${STUDY_USER_QUOTA:-100M}"

log() { echo "provision-study-user: $*"; }

if [[ ! -r $secret_file ]]; then
  log "no readable password file at $secret_file; skipping (the app will not be able to log in)"
  exit 1
fi
password="$(<"$secret_file")"
password="${password%"${password##*[![:space:]]}"}"  # drop trailing whitespace, e.g. a CR

if [[ ! $user =~ ^[A-Za-z][A-Za-z0-9_]{0,29}$ ]]; then
  log "invalid user name: $user"; exit 1
fi
if [[ -z $password || $password == *[\"\'\&]* ]]; then
  log "the password must be non-empty and must not contain quotes or &"; exit 1
fi
if [[ ! $quota =~ ^[0-9]+[KMGT]?$|^UNLIMITED$ ]]; then
  log "invalid quota: $quota"; exit 1
fi

"${ORACLE_HOME}/bin/sqlplus" -s -L / as sysdba <<SQL
WHENEVER SQLERROR EXIT FAILURE
SET FEEDBACK OFF VERIFY OFF ECHO OFF DEFINE OFF
ALTER SESSION SET CONTAINER = ${pdb};
DECLARE
  user_count    PLS_INTEGER;
  profile_count PLS_INTEGER;
BEGIN
  -- A learning account should not expire after the default 180 days.
  SELECT COUNT(*) INTO profile_count FROM dba_profiles WHERE profile = 'ORASTUDY_PROFILE';
  IF profile_count = 0 THEN
    EXECUTE IMMEDIATE 'CREATE PROFILE orastudy_profile LIMIT PASSWORD_LIFE_TIME UNLIMITED';
  END IF;
  SELECT COUNT(*) INTO user_count FROM dba_users WHERE username = UPPER('${user}');
  IF user_count = 0 THEN
    EXECUTE IMMEDIATE 'CREATE USER ${user} IDENTIFIED BY "${password}" DEFAULT TABLESPACE users '
                   || 'QUOTA ${quota} ON users PROFILE orastudy_profile';
  ELSE
    EXECUTE IMMEDIATE 'ALTER USER ${user} IDENTIFIED BY "${password}" ACCOUNT UNLOCK PROFILE orastudy_profile';
  END IF;
END;
/
GRANT CREATE SESSION, CREATE TABLE, CREATE VIEW, CREATE SEQUENCE, CREATE SYNONYM TO ${user};
EXIT
SQL
status=$?
if (( status == 0 )); then log "user ${user^^} is ready in ${pdb}"; else log "failed (status $status)"; fi
exit "$status"
