FROM node:24-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS backend-deps
WORKDIR /app
RUN python -m venv /opt/venv
COPY backend/requirements.txt ./
RUN /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim AS runtime
ARG VERSION=dev
WORKDIR /app
COPY --from=backend-deps /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" APP_VERSION=${VERSION}
COPY backend/app ./app
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist
RUN useradd -u 1000 -m appuser && mkdir -p /data && chmod 777 /data
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/live', timeout=3)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
