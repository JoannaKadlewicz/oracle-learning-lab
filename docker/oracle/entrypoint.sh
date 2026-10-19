#!/usr/bin/env bash
# Entrypoint of the all-in-one image: supervises Oracle Database 19c and the Oracle Learning Lab app.
#
#   1. start the database (the base image's runOracle.sh: creates it on first start, runs
#      /opt/oracle/scripts/startup/* on every start, which provisions the ORASTUDY user)
#   2. wait until it is open (checkDBStatus.sh), however long the first creation takes
#   3. create the sample schema if it is missing (oracle-lab init-db)
#   4. serve the app
#
# If either process exits, the other is stopped and the container exits non-zero, so the
# restart policy brings both back. On SIGTERM (docker stop) the app stops first, then the
# database runs SHUTDOWN IMMEDIATE (runOracle.sh traps SIGTERM): give `docker stop` enough time.
set -Euo pipefail

readonly POLL_SECONDS=10
db_pid=""
app_pid=""

log() { printf '%s [entrypoint] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

is_running() { [[ -n $1 ]] && kill -0 "$1" 2>/dev/null; }

stop_process() {  # pid name
  if is_running "$1"; then
    log "stopping $2"
    kill -TERM "$1" 2>/dev/null || true
    wait "$1" 2>/dev/null || true
  fi
}

shutdown() {
  stop_process "$app_pid" "the app"
  stop_process "$db_pid" "the database"
}

# shellcheck disable=SC2317  # invoked by the traps below
on_signal() {
  log "received $1"
  shutdown
  exit 0
}
trap 'on_signal SIGTERM' TERM
trap 'on_signal SIGINT' INT

# `sleep` in the background and `wait` for it, so signals are handled at once, not after the sleep.
pause() { sleep "$1" & wait $!; }

log "starting Oracle Database (SID ${ORACLE_SID:-ORCLCDB}, PDB ${ORACLE_PDB})"
"${ORACLE_BASE}/${RUN_FILE}" &
db_pid=$!

until "${ORACLE_BASE}/${CHECK_DB_FILE}" >/dev/null 2>&1; do
  if ! is_running "$db_pid"; then
    wait "$db_pid"
    log "the database exited during startup (status $?)"
    exit 1
  fi
  pause "$POLL_SECONDS"
done
log "database is open"

if ! oracle-lab init-db; then
  log "preparing the sample schema failed"
  shutdown
  exit 1
fi

oracle-lab serve &
app_pid=$!
log "app started (pid $app_pid)"

# bash 4.2 (Oracle Linux 7) has no `wait -n`, so poll until one of the two processes is gone.
while is_running "$db_pid" && is_running "$app_pid"; do
  pause "$POLL_SECONDS"
done
if is_running "$db_pid"; then exited="the app" pid=$app_pid; else exited="the database" pid=$db_pid; fi
wait "$pid"
status=$?
log "$exited exited unexpectedly (status $status)"
shutdown
exit $(( status == 0 ? 1 : status ))
