# syntax=docker/dockerfile:1.7
#
# The app alone, for a database that runs elsewhere (Render, CI, an existing Oracle server).
#     docker build -f docker/app.Dockerfile -t oracle-learning-lab-app .
# Configure it with the STUDY_* variables (see src/oracle_lab/config.py); mount passwords as
# files and point STUDY_PASSWORD_FILE / STUDY_AUTH_PASSWORD_FILE at them.

FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install . && rm -rf /srv/src

RUN useradd --uid 10001 --create-home study && install -d -o study -g study /var/lib/oracle-lab
USER study

ENV STUDY_HOST=0.0.0.0 \
    STUDY_PORT=8071 \
    STUDY_DATA_DIR=/var/lib/oracle-lab

EXPOSE 8071
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s CMD ["oracle-lab", "healthcheck"]

# Wait for the database, create the sample schema on first start, then serve.
CMD ["sh", "-c", "oracle-lab init-db && exec oracle-lab serve"]
