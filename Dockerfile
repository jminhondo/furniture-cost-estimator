# ── Builder stage ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build tools
RUN pip install --upgrade pip

# Copy dependency manifest first (better layer caching)
COPY pyproject.toml .

# Install all Python dependencies into a separate prefix
RUN pip install --prefix=/install -e . --no-deps || true
RUN pip install --prefix=/install \
    anthropic \
    fastapi \
    "uvicorn[standard]" \
    "sqlalchemy[asyncio]" \
    asyncpg \
    pydantic \
    "pydantic-settings" \
    pandas \
    scikit-learn \
    joblib \
    rectpack \
    pdf2image \
    reportlab \
    openpyxl \
    ezdxf \
    redis \
    python-dotenv \
    httpx \
    alembic \
    "python-multipart" \
    PyYAML

# ── Runtime stage ──────────────────────────────────────────────────────────
FROM python:3.12-slim

# System deps: poppler for pdf2image, curl for health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY src/       src/
COPY configs/   configs/
COPY alembic/   alembic/
COPY alembic.ini .

# Create directories used at runtime
RUN mkdir -p /tmp/furniture_uploads /tmp/furniture_quotes models

# Non-root user for security
RUN useradd -m appuser && chown -R appuser /app /tmp/furniture_uploads /tmp/furniture_quotes /app/models
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8000}
