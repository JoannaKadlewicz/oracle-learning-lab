# syntax=docker/dockerfile:1.7
#
# Oracle Learning Lab, all in one image: Oracle Database 19c Enterprise Edition and the web app.
#
# Oracle does not publish a pullable 19c image, so the base is the image you build once with
# Oracle's official scripts (https://github.com/oracle/docker-images, OracleDatabase/SingleInstance):
#     ./buildContainerImage.sh -v 19.3.0 -e      ->  oracle/database:19.3.0-ee
# and pass its tag as ORACLE_BASE_IMAGE (see .env.example). The app needs a modern Python, which
# Oracle Linux 7 does not have, so a standalone CPython build is added next to the database.
#
# Usually built and run with docker compose; see docs/docker.md.

ARG ORACLE_BASE_IMAGE=oracledb:19.3.0
ARG UV_VERSION=0.12.10

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# ---------------------------------------------------------------------------------------- build
# Built on the runtime OS, so the interpreter and the wheels match its glibc (2.17).
FROM ${ORACLE_BASE_IMAGE} AS build
ARG PYTHON_VERSION=3.14.4
USER root
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PYTHON_INSTALL_DIR=/opt/python \
    UV_PYTHON_PREFERENCE=only-managed \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
RUN --mount=type=cache,target=/root/.cache/uv \
    uv python install "${PYTHON_VERSION}" \
 && uv venv --python "${PYTHON_VERSION}" /opt/oracle-lab/venv

# Dependencies first, so editing the app does not reinstall them.
COPY pyproject.toml README.md /src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --python /opt/oracle-lab/venv/bin/python -r /src/pyproject.toml
COPY src /src/src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --python /opt/oracle-lab/venv/bin/python --no-deps /src \
 && /opt/oracle-lab/venv/bin/oracle-lab --version

# -------------------------------------------------------------------------------------- runtime
FROM ${ORACLE_BASE_IMAGE}

LABEL org.opencontainers.image.title="Oracle Learning Lab" \
      org.opencontainers.image.description="Study app for 1Z0-071 / 1Z0-171 with Oracle Database 19c"

USER root
COPY --from=build /opt/python /opt/python
COPY --from=build /opt/oracle-lab/venv /opt/oracle-lab/venv
COPY --chmod=0755 docker/oracle/entrypoint.sh docker/oracle/healthcheck.sh docker/oracle/provision-study-user.sh \
     /opt/oracle-lab/bin/
COPY --chmod=0644 docker/oracle/startup/ /opt/oracle/scripts/startup/
# The app's data directory; a bind mount over it must be writable by uid 54321 (oracle).
RUN install -d -o oracle -g oinstall -m 0750 /var/lib/oracle-lab
USER oracle

# Non-secret configuration only. Passwords come from Docker secrets mounted under /run/secrets:
#   oracle_pwd            SYS/SYSTEM/PDBADMIN (read by the base image's runOracle.sh)
#   study_db_password     the learning user ORASTUDY (read by provision-study-user.sh and the app)
#   study_auth_password   web login (optional; an empty file turns the login off)
ENV PATH=/opt/oracle-lab/venv/bin:${PATH} \
    PYTHONUNBUFFERED=1 \
    ORACLE_SID=ORCLCDB \
    ORACLE_PDB=ORAPDB1 \
    ORACLE_CHARACTERSET=AL32UTF8 \
    STUDY_HOST=0.0.0.0 \
    STUDY_PORT=8071 \
    STUDY_DSN=localhost:1521/ORAPDB1 \
    STUDY_USER=orastudy \
    STUDY_DATA_DIR=/var/lib/oracle-lab \
    STUDY_PASSWORD_FILE=/run/secrets/study_db_password \
    STUDY_INIT_TIMEOUT=600

EXPOSE 8071 1521

# The first start creates the database, which takes 10-30 minutes; later starts take about one.
HEALTHCHECK --interval=30s --timeout=30s --start-period=45m --retries=3 \
    CMD ["/opt/oracle-lab/bin/healthcheck.sh"]

STOPSIGNAL SIGTERM
ENTRYPOINT ["/opt/oracle-lab/bin/entrypoint.sh"]
CMD []
