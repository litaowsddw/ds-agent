FROM python:3.11-slim

WORKDIR /app

COPY apps/api/requirements.txt /app/apps/api/requirements.txt
RUN pip install --no-cache-dir -r /app/apps/api/requirements.txt

COPY apps /app/apps
COPY packages /app/packages

ENV PYTHONPATH=/app:/app/apps/api:/app/packages/runtime:/app/packages/workflow

CMD ["uvicorn", "apps.api.app.main:app", "--host", "0.0.0.0", "--port", "8000"]

