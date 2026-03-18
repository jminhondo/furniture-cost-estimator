"""
Pipeline router — POST /api/v1/projects/analyze

Also contains ``run_pipeline()``, the async background task that drives
the full Capa 1 → 2 → 3 → 4 execution and writes progress to Redis.

Redis state shape
-----------------
Key:  ``project:{project_id}``
TTL:  24 h
Value (JSON):
    {
        "project_id": str,
        "status": "processing|parsing|bom|costs|quoting|done|error",
        "progress": {"parsing": 0-100, "bom": 0-100, "costs": 0-100, "quoting": 0-100},
        "file_path": str,
        "file_type": "skp|pdf",
        "metadata": dict,
        "layer1": dict | null,
        "layer2": dict | null,
        "layer3": dict | null,
        "layer4": dict | null,
        "error": str | null,
        "created_at": ISO str,
        "updated_at": ISO str,
    }
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

import redis.asyncio as aioredis
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile

from src.api.deps import get_config, get_quote_output_dir, get_redis, get_upload_dir
from src.api.schemas import AnalyzeResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/projects", tags=["pipeline"])

_PROJECT_TTL = 86_400          # 24 h
_ALLOWED_EXTENSIONS = {".skp", ".pdf"}


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/analyze", response_model=AnalyzeResponse, status_code=202)
async def analyze(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    metadata: str = Form("{}"),
    redis: aioredis.Redis = Depends(get_redis),
    config: dict = Depends(get_config),
    upload_dir: Path = Depends(get_upload_dir),
    quote_output_dir: Path = Depends(get_quote_output_dir),
) -> AnalyzeResponse:
    """
    Upload a .skp or .pdf file and kick off the full estimation pipeline.

    The heavy work runs as a background task; this endpoint returns
    immediately with a ``project_id`` that can be polled via
    ``GET /api/v1/projects/{id}/status``.
    """
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type '{suffix}'. Allowed: {_ALLOWED_EXTENSIONS}",
        )

    project_id = str(uuid.uuid4())

    # ── Save uploaded file ────────────────────────────────────────────────
    project_upload_dir = upload_dir / project_id
    project_upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = project_upload_dir / (file.filename or f"upload{suffix}")
    content = await file.read()
    file_path.write_bytes(content)

    # ── Parse metadata ────────────────────────────────────────────────────
    try:
        meta = json.loads(metadata)
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="metadata must be valid JSON")

    # ── Initialize Redis state ────────────────────────────────────────────
    now = datetime.now(timezone.utc).isoformat()
    state = {
        "project_id": project_id,
        "status": "processing",
        "progress": {"parsing": 0, "bom": 0, "costs": 0, "quoting": 0},
        "file_path": str(file_path),
        "file_type": suffix.lstrip("."),
        "metadata": meta,
        "layer1": None,
        "layer2": None,
        "layer3": None,
        "layer4": None,
        "error": None,
        "created_at": now,
        "updated_at": now,
    }
    await redis.set(f"project:{project_id}", json.dumps(state), ex=_PROJECT_TTL)

    # ── Start background pipeline ─────────────────────────────────────────
    background_tasks.add_task(
        run_pipeline,
        project_id, file_path, suffix.lstrip("."),
        meta, config, redis, quote_output_dir,
    )

    logger.info("Project %s created, pipeline queued (file=%s)", project_id, file.filename)
    return AnalyzeResponse(project_id=project_id, status="processing")


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------

async def run_pipeline(
    project_id: str,
    file_path: Path,
    file_type: str,
    metadata: dict,
    config: dict,
    redis: aioredis.Redis,
    quote_output_dir: Path,
) -> None:
    """
    Execute Capa 1 → 2 → 3 → 4 and write progress to Redis after each step.

    Imported by integration tests to be replaced with a lightweight mock.
    """

    async def _update(updates: dict) -> None:
        raw = await redis.get(f"project:{project_id}")
        if raw is None:
            return
        current = json.loads(raw)
        current.update(updates)
        current["updated_at"] = datetime.now(timezone.utc).isoformat()
        await redis.set(f"project:{project_id}", json.dumps(current), ex=_PROJECT_TTL)

    try:
        # ── Layer 1: parse ────────────────────────────────────────────────
        await _update({"status": "parsing", "progress": {"parsing": 10, "bom": 0, "costs": 0, "quoting": 0}})

        proyecto_id = metadata.get("proyecto_id", project_id)

        if file_type == "skp":
            from src.agents.skp_parser import SKPParserAgent
            agent = SKPParserAgent()
            layer1 = await agent.parse(str(file_path), proyecto_id=proyecto_id)
        else:
            from src.agents.pdf_vision_agent import PDFVisionAgent
            agent = PDFVisionAgent()
            layer1 = await agent.parse(str(file_path), proyecto_id=proyecto_id)

        await _update({
            "layer1": layer1,
            "progress": {"parsing": 100, "bom": 0, "costs": 0, "quoting": 0},
        })
        logger.debug("Project %s — layer1 done (%d components)", project_id,
                     len(layer1.get("componentes", [])))

        # ── Layer 2: BOM ──────────────────────────────────────────────────
        await _update({"status": "bom", "progress": {"parsing": 100, "bom": 10, "costs": 0, "quoting": 0}})

        from src.layers.layer2_bom import BOMBuilder
        layer2 = BOMBuilder(config).build(layer1)

        await _update({
            "layer2": layer2,
            "progress": {"parsing": 100, "bom": 100, "costs": 0, "quoting": 0},
        })
        logger.debug("Project %s — layer2 done (%d tableros)", project_id,
                     len(layer2.get("tableros", [])))

        # ── Layer 3: costs ────────────────────────────────────────────────
        await _update({"status": "costs", "progress": {"parsing": 100, "bom": 100, "costs": 10, "quoting": 0}})

        from src.layers.layer3_costs import CostEngine
        project_params = metadata.get("project_params", {})
        layer3 = await CostEngine(config).estimate(layer2, project_params)

        await _update({
            "layer3": layer3,
            "progress": {"parsing": 100, "bom": 100, "costs": 100, "quoting": 0},
        })
        logger.debug("Project %s — layer3 done (total=%.2f)", project_id,
                     layer3.get("costo_total_usd", 0))

        # ── Layer 4: quote ────────────────────────────────────────────────
        await _update({"status": "quoting", "progress": {"parsing": 100, "bom": 100, "costs": 100, "quoting": 10}})

        from src.agents.quote_generator import QuoteGenerator
        gen = QuoteGenerator(config, output_dir=quote_output_dir / project_id)
        quote_data = {
            "proyecto_id": proyecto_id,
            "proyecto_nombre": metadata.get("proyecto_nombre", proyecto_id),
            "cliente": metadata.get("cliente", {}),
            "layer2": layer2,
            "layer3": layer3,
        }
        layer4 = await gen.generate(quote_data)

        await _update({
            "layer4": layer4,
            "status": "done",
            "progress": {"parsing": 100, "bom": 100, "costs": 100, "quoting": 100},
        })
        logger.info("Project %s — pipeline done (quote=%s)", project_id,
                    layer4.get("quote_number"))

    except Exception as exc:
        logger.exception("Pipeline failed for project %s", project_id)
        await _update({"status": "error", "error": str(exc)})
