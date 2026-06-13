# ════════════════════════════════════════════════════════════════════════════════
# RailMind Backend - Production Dockerfile
# Multi-stage build for optimized image size
# Python 3.11+ | FastAPI | PostgreSQL | Redis
# ════════════════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────────────────────────
# Stage 1: Builder - Install dependencies
# ─────────────────────────────────────────────────────────────────────────────────
FROM python:3.14-slim@sha256:d7a925f9eb9639a93e455b9f12c167569358818c0f62b51b88edbc8fcf34c421 AS builder

WORKDIR /app

# Install system dependencies required for Python packages (PostgreSQL, etc.)
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first (Docker layer caching optimization)
COPY requirements.txt .

# Install Python dependencies
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install -r requirements.txt

# ─────────────────────────────────────────────────────────────────────────────────
# Stage 2: Runtime - Minimal production image
# ─────────────────────────────────────────────────────────────────────────────────
FROM python:3.14-slim@sha256:d7a925f9eb9639a93e455b9f12c167569358818c0f62b51b88edbc8fcf34c421

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PORT=8000

# Create non-root user for security (GCP Cloud Run best practice)
RUN useradd -m -u 1000 railmind && \
    mkdir -p /app && \
    chown -R railmind:railmind /app

# Install runtime dependencies only (lighter than builder stage)
RUN apt-get update && apt-get install -y \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed packages from builder stage
COPY --from=builder /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=railmind:railmind . .

# Switch to non-root user
USER railmind

# Expose port (Cloud Run will inject PORT env var, default 8000)
EXPOSE 8000

# Health check for container orchestration
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT}/api/v1/health-check/health-check-status || exit 1

# Run FastAPI with uvicorn
# Cloud Run will use PORT env var, fallback to 8000
# WEB_CONCURRENCY tunes worker count per box (2 is sane for a small VM;
# raise towards CPU core count on bigger instances)
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips="*" --timeout-keep-alive 65