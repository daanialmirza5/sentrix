# Single-container SENTRIX: API + built console + MiniLM ONNX model. Listens on $PORT (default 8000).
FROM node:22-alpine AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npx vite build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    SENTRIX_DATA_DIR=/app/data SENTRIX_AUTO_SEED=1
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt
COPY scripts/download_model.py scripts/download_model.py
RUN python scripts/download_model.py
COPY backend/app backend/app
COPY reports/drift_eval.json reports/drift_eval.json
COPY --from=ui /ui/dist frontend/dist
# uid 1000: Hugging Face Spaces runs containers as uid 1000; harmless on other hosts.
RUN useradd --create-home --uid 1000 sentrix && chown -R sentrix /app
USER sentrix
WORKDIR /app/backend
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s CMD python -c "import os,urllib.request;urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/v1/health')"
CMD ["sh", "-c", "exec python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
