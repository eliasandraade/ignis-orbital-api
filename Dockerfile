FROM python:3.12-slim

WORKDIR /app

# Dependencies come only from the hash-locked export of uv.lock, as prebuilt
# wheels: no unpinned resolution and no setup.py execution at build time.
# Regenerate after changing pyproject.toml:
#   uv lock && uv export --frozen --no-dev --no-emit-project \
#     --format requirements-txt -o requirements.lock
COPY requirements.lock ./
RUN pip install --no-cache-dir --require-hashes --only-binary :all: -r requirements.lock

# The app runs from /app (uvicorn app.main:app, alembic, python -m seed);
# it is not installed as a package.
COPY . .

# Code stays owned by root (read-only for the runtime user).
ENV PYTHONDONTWRITEBYTECODE=1
RUN chmod +x /app/scripts/entrypoint.sh \
    && useradd --create-home --uid 10001 ignis

# Run as an unprivileged user (Sonar hotspot docker:S6471).
USER ignis

EXPOSE 8000

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
