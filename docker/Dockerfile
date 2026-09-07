FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY pyproject.toml uv.lock ./

COPY . .

RUN chown -R app:app /app

USER app
ENV HOME=/tmp

EXPOSE 8000

FROM base AS api
RUN pip install --no-cache-dir .
CMD ["python", "-m", "uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS worker
RUN pip install --no-cache-dir .
CMD ["python", "-m", "app.worker.main"]

FROM base AS migrate
RUN pip install --no-cache-dir .
CMD ["python", "-m", "alembic", "upgrade", "head"]

FROM base AS redis-init
RUN pip install --no-cache-dir .
CMD ["python", "scripts/init-redis-streams.py"]