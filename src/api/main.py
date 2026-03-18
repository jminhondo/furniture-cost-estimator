"""
FastAPI application — Furniture Cost Estimator API.

Startup
-------
The ``lifespan`` context manager:
  1. Connects to Redis (non-fatal — app starts even if Redis is unreachable)
  2. Loads ``configs/defaults.yml``
  3. Creates the shared ``MLTrainingPipeline`` singleton
  4. Ensures upload and quote output directories exist

CORS
----
Origins are configurable via the ``CORS_ORIGINS`` env var
(comma-separated list, defaults to ``*`` for development).

Docs
----
Interactive docs at ``/docs``  (Swagger UI)
Alternative at   ``/redoc``   (ReDoc)
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
import yaml
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.agents.tools.training_pipeline import MLTrainingPipeline
from src.api.deps import QUOTE_OUTPUT_DIR, UPLOAD_DIR
from src.api.routers import ml, pipeline, projects

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = (
    __import__("pathlib").Path(__file__).parent.parent.parent / "configs" / "defaults.yml"
)


def _load_config() -> dict:
    with _DEFAULT_CONFIG_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Redis — non-fatal if unavailable; tests override the dependency
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    try:
        client = aioredis.from_url(redis_url, decode_responses=True)
        await client.ping()
        app.state.redis = client
        logger.info("Redis connected: %s", redis_url)
    except Exception as exc:
        logger.warning("Redis unavailable at startup (%s) — endpoints will return 503", exc)
        app.state.redis = None

    # Config
    app.state.config = _load_config()

    # ML training pipeline
    app.state.training_pipeline = MLTrainingPipeline()

    # Ensure directories exist
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    QUOTE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    yield

    if app.state.redis is not None:
        await app.state.redis.aclose()


# ---------------------------------------------------------------------------
# App factory (makes unit-testable)
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    app = FastAPI(
        title="Furniture Cost Estimator",
        description=(
            "AI-agent pipeline for estimating furniture fabrication and "
            "installation costs from SketchUp (.skp) and PDF plans."
        ),
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS
    origins_raw = os.getenv("CORS_ORIGINS", "*")
    origins = [o.strip() for o in origins_raw.split(",")] if origins_raw != "*" else ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(pipeline.router)
    app.include_router(projects.router)
    app.include_router(ml.router)

    @app.get("/health", tags=["health"])
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
