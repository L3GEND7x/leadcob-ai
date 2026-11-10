FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend /app/backend
COPY alembic.ini /app/alembic.ini
COPY frontend /app/frontend
COPY config /app/config
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/backend
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--app-dir", "/app/backend", "--host", "0.0.0.0", "--port", "8000"]
