FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.3 /uv /usr/local/bin/uv
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --extra cpu --no-dev --no-install-project --no-cache
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic
RUN uv sync --locked --extra cpu --no-dev --no-cache && useradd --create-home appuser \
    && mkdir -p /data/uploads /data/models && chown -R appuser:appuser /data
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=10s --start-period=30s --retries=5 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/papers?limit=1', timeout=8)"
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
