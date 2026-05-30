FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
# Install build backend first so pip can resolve editable install metadata
RUN pip install --no-cache-dir hatchling
# Create minimal package stub so editable install can register paths
RUN mkdir -p app && touch app/__init__.py
RUN pip install --no-cache-dir -e .

COPY . .

RUN chmod +x /app/scripts/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
