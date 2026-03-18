"""
FastAPI dependency providers.

All heavy objects (Redis, config, training pipeline) live in ``app.state``
and are set during the lifespan in ``main.py``.  These functions expose
them as FastAPI dependencies so routers stay testable via
``app.dependency_overrides``.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import HTTPException, Request

import redis.asyncio as aioredis

from src.agents.tools.training_pipeline import MLTrainingPipeline

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/tmp/furniture_uploads"))
QUOTE_OUTPUT_DIR = Path(os.getenv("QUOTE_OUTPUT_DIR", "/tmp/furniture_quotes"))


async def get_redis(request: Request) -> aioredis.Redis:
    """Return the shared Redis async client from app state."""
    client = getattr(request.app.state, "redis", None)
    if client is None:
        raise HTTPException(status_code=503, detail="Redis not available")
    return client


def get_config(request: Request) -> dict:
    """Return the pre-loaded YAML config from app state."""
    return request.app.state.config


def get_training_pipeline(request: Request) -> MLTrainingPipeline:
    """Return the shared MLTrainingPipeline singleton from app state."""
    return request.app.state.training_pipeline


def get_upload_dir() -> Path:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOAD_DIR


def get_quote_output_dir() -> Path:
    QUOTE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return QUOTE_OUTPUT_DIR
