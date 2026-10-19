# shellcheck shell=bash
# Sourced (not executed) by the base image's runUserScripts.sh on every database start.
# An `exit` here would end runOracle.sh, so the work happens in a separate process.
/opt/oracle-lab/bin/provision-study-user.sh || echo "WARNING: provisioning the study user failed; see above"
