FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --timeout 120 --retries 5 -r backend/requirements.txt && useradd --uid 10001 --create-home aiops
COPY backend /app/backend
COPY evals /app/evals
RUN chown -R aiops:aiops /app
USER aiops
ARG APP_REVISION=unknown
LABEL org.opencontainers.image.revision=$APP_REVISION
EXPOSE 8000
CMD ["sh", "-c", "alembic -c backend/alembic.ini upgrade head && uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers 1"]
