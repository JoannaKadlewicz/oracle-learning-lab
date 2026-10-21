# shellcheck shell=bash
# Sourced (not executed) by the base image's runUserScripts.sh on every database start, after
# 01-provision-study-user.sh. An `exit` here would end runOracle.sh, so the work happens in a
# separate process.
/opt/oracle-lab/bin/provision-practice-users.sh || echo "WARNING: provisioning the practice users failed; see above"
