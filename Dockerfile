FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TRANSFORMERS_CACHE=/app/model_cache
ENV SENTENCE_TRANSFORMERS_HOME=/app/model_cache

# Create non-root user for security
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

# Install OS dependencies required by FAISS, pandas, and sentence-transformers
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create model cache directory with proper permissions
RUN mkdir -p /app/model_cache && chown -R appuser:appgroup /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy codebase
COPY --chown=appuser:appgroup . .

# Ensure upload and dynamic frontend directories exist with proper permissions
RUN mkdir -p uploads frontend/graphs logs && \
    chown -R appuser:appgroup uploads frontend logs

# Switch to non-root user
USER appuser

# Expose the API port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/api/health || exit 1

# Start the FastAPI Uvicorn Server with graceful shutdown
# Using --workers 1 for simplicity in container; increase for production
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080", "--timeout-keep-alive", "5"]
