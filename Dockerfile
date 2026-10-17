# Oracle Learning Lab (1Z0-071 study app). Normally started with docker compose (see docs/docker.md).
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    STUDY_HOST=0.0.0.0 \
    STUDY_PORT=8071

WORKDIR /srv

COPY app/requirements.txt app/requirements.txt
RUN pip install -r app/requirements.txt

COPY app/ app/

# Unprivileged user; state/ and notes/personal/ are volume mount points owned by it,
# so named volumes start with the right ownership.
RUN useradd --create-home --uid 10001 study \
    && mkdir -p app/state app/notes/personal \
    && chown -R study:study app/state app/notes/personal
USER study

EXPOSE 8071

# Wait for the database, create the sample schema on first start, then serve.
CMD ["sh", "-c", "python app/init_db.py && exec python app/server.py"]
