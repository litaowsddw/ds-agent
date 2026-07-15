FROM python:3.11-slim

WORKDIR /app

COPY apps/worker/requirements.txt /app/apps/worker/requirements.txt
COPY apps/api/requirements.txt /app/apps/api/requirements.txt
RUN pip install --no-cache-dir -r /app/apps/worker/requirements.txt -r /app/apps/api/requirements.txt

COPY apps /app/apps
COPY packages /app/packages

ENV PYTHONPATH=/app:/app/apps/api:/app/apps/worker:/app/packages/runtime:/app/packages/workflow

CMD ["celery", "-A", "apps.worker.app.celery_app:celery_app", "worker", "--loglevel=INFO", "-Q", "workflow.default,background.memory,background.mcp"]

