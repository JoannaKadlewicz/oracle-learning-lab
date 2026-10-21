#!/usr/bin/env bash
# Generate the passwords docker compose mounts as secrets. Existing files are kept, so running it
# again is safe; delete a file and rerun to rotate that password (then restart the stack).
#
#   secrets/oracle_pwd            SYS, SYSTEM and PDBADMIN
#   secrets/study_db_password     the learning user ORASTUDY
#   secrets/provisioner_password OLL_PROVISIONER, creates the learners' private practice schemas
#   secrets/gateway_password      OLL_GATEWAY, the proxy user the app connects through
#
# The folder is private to you (0700). The files are 0644 because Oracle reads them inside the
# container as another user (uid 54321), and Compose cannot change the owner of file secrets.
set -Eeuo pipefail

dir="${1:-$(dirname "$0")/../secrets}"
umask 077
mkdir -p "$dir"
chmod 0700 "$dir"

# Oracle passwords: letters and digits only (no quoting problems in SQL), starting with a letter.
generate() { printf 'S%s\n' "$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 23)"; }

for name in oracle_pwd study_db_password provisioner_password gateway_password; do
  file="$dir/$name"
  if [[ -e $file ]]; then
    echo "kept      $file"
  else
    generate >"$file"
    echo "generated $file"
  fi
  chmod 0644 "$file"
done
