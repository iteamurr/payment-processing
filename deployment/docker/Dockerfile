FROM python:3.12-slim AS build

RUN pip install --no-cache-dir poetry==2.4.1
WORKDIR /app
COPY pyproject.toml poetry.lock ./
RUN python -m venv /opt/venv \
    && VIRTUAL_ENV=/opt/venv poetry install --no-root --only main --no-interaction

FROM python:3.12-slim

COPY --from=build /opt/venv /opt/venv
WORKDIR /app
COPY alembic.ini ./
COPY migrations ./migrations
COPY src ./src

RUN useradd --create-home --uid 10001 appuser
USER appuser

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src
EXPOSE 8000
CMD ["uvicorn", "payments_processing.presentation.api.app:build_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
