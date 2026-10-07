FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir poetry==2.4.1
COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false \
    && poetry install --no-root --only main

COPY alembic.ini ./
COPY migrations ./migrations
COPY src ./src

RUN useradd --create-home --uid 10001 appuser
USER appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src
EXPOSE 8000
CMD ["uvicorn", "payments_processing.presentation.app:build_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
