# Flask RAG API (works on ARM/aarch64 and x86)
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/models

# Tesseract reads scanned PDF pages (OCR) during ingest
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# CPU-only PyTorch (much smaller than the default GPU build)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Download both models at build time, so the container never needs Hugging Face at runtime.
# Keep these names in sync with EMBEDDING_MODEL and RERANK_MODEL in app/core/config.py.
ARG EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2
ARG RERANK_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer('${EMBEDDING_MODEL}'); CrossEncoder('${RERANK_MODEL}')"
ENV HF_HUB_OFFLINE=1

COPY . .
RUN useradd --create-home app && chown -R app /app
USER app

EXPOSE 5000
# 1 worker: models are loaded once (saves RAM), and the live-update hub lives in memory.
# Threads serve parallel requests; a streaming answer or an open WebSocket holds one thread each.
CMD ["gunicorn", "app.main:create_app()", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "64", "--timeout", "300"]
