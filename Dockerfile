FROM python:3.11-slim AS base

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for security
RUN groupadd -r aura && useradd -r -g aura -d /app -s /sbin/nologin aura

WORKDIR /app

# Install Python dependencies (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Ensure data directories exist
RUN mkdir -p data/memory data/knowledge_graph data/semantic_memory data/uploads data/generated_images logs \
    && chown -R aura:aura /app

USER aura

# Environment
ENV AURA_HOST=127.0.0.1 \
    AURA_PORT=8000 \
    AURA_ENV=production \
    PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"

CMD ["python3", "-m", "uvicorn", "interface.server:app", "--host", "127.0.0.1", "--port", "8000"]
