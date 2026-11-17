# Backend image: FastAPI API for the Capital Drift Monitor.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    CD_DATA_DIR=/data

WORKDIR /app

COPY pyproject.toml alembic.ini ./
COPY migrations ./migrations
COPY app ./app
# The results page reads this offline results file (settings.capital_results_file -> /app/results/).
COPY results ./results
# Postgres extras included so the same image runs on SQLite (default) or Postgres.
RUN pip install --upgrade pip && pip install ".[postgres]"

# Run as an unprivileged user; /data holds the SQLite database.
RUN useradd --create-home --uid 10001 app && mkdir -p /data && chown app /data
USER app
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
