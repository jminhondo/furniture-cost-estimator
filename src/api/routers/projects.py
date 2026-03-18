"""
Projects router — result endpoints for a completed/in-progress project.

All endpoints read from Redis state written by ``run_pipeline()``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from src.api.deps import (
    get_config,
    get_quote_output_dir,
    get_redis,
    get_training_pipeline,
)
from src.api.schemas import (
    BOMResponse,
    CloseProjectRequest,
    CloseProjectResponse,
    CostsResponse,
    LayerProgress,
    ProjectStatusResponse,
    QuoteFilesResponse,
    RegenerateRequest,
    RegenerateResponse,
)
from src.agents.tools.training_pipeline import MLTrainingPipeline
from src.layers.layer3_costs import _extract_features

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_state(project_id: str, redis: aioredis.Redis) -> dict:
    """Fetch project state from Redis; raise 404 if missing."""
    raw = await redis.get(f"project:{project_id}")
    if raw is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return json.loads(raw)


def _require_done(state: dict) -> None:
    """Raise 409 if the project has not finished the pipeline."""
    status = state.get("status", "")
    if status == "error":
        raise HTTPException(status_code=500,
                            detail=f"Pipeline failed: {state.get('error', 'unknown error')}")
    if status != "done":
        raise HTTPException(status_code=409,
                            detail=f"Project not ready (status='{status}'). "
                                   "Poll /status until done.")


# ---------------------------------------------------------------------------
# GET /{project_id}/status
# ---------------------------------------------------------------------------

@router.get("/{project_id}/status", response_model=ProjectStatusResponse)
async def get_status(
    project_id: str,
    redis: aioredis.Redis = Depends(get_redis),
) -> ProjectStatusResponse:
    """Return current pipeline status and per-layer progress (0–100)."""
    state = await _get_state(project_id, redis)
    return ProjectStatusResponse(
        project_id=project_id,
        status=state["status"],
        progress=LayerProgress(**state.get("progress", {})),
        created_at=state["created_at"],
        updated_at=state["updated_at"],
        error=state.get("error"),
    )


# ---------------------------------------------------------------------------
# GET /{project_id}/bom
# ---------------------------------------------------------------------------

@router.get("/{project_id}/bom", response_model=BOMResponse)
async def get_bom(
    project_id: str,
    redis: aioredis.Redis = Depends(get_redis),
) -> BOMResponse:
    """Return the Layer-2 BOM JSON (tableros + herrajes + resumen)."""
    state = await _get_state(project_id, redis)
    _require_done(state)
    layer2 = state.get("layer2")
    if not layer2:
        raise HTTPException(status_code=404, detail="BOM not available")
    return BOMResponse(project_id=project_id, bom=layer2)


# ---------------------------------------------------------------------------
# GET /{project_id}/costs
# ---------------------------------------------------------------------------

@router.get("/{project_id}/costs", response_model=CostsResponse)
async def get_costs(
    project_id: str,
    redis: aioredis.Redis = Depends(get_redis),
) -> CostsResponse:
    """Return the Layer-3 cost breakdown with ML confidence scores."""
    state = await _get_state(project_id, redis)
    _require_done(state)
    layer3 = state.get("layer3")
    if not layer3:
        raise HTTPException(status_code=404, detail="Cost breakdown not available")
    return CostsResponse(project_id=project_id, costs=layer3)


# ---------------------------------------------------------------------------
# GET /{project_id}/quote
# ---------------------------------------------------------------------------

@router.get("/{project_id}/quote", response_model=QuoteFilesResponse)
async def get_quote(
    project_id: str,
    request: Request,
    redis: aioredis.Redis = Depends(get_redis),
) -> QuoteFilesResponse:
    """Return download URLs for the PDF (resumido + detallado) and Excel."""
    state = await _get_state(project_id, redis)
    _require_done(state)
    layer4 = state.get("layer4")
    if not layer4:
        raise HTTPException(status_code=404, detail="Quote not available")

    base = str(request.base_url).rstrip("/")
    quote_num = layer4.get("quote_number", "")

    # Map stored absolute paths → API download URLs
    files_raw: dict = layer4.get("files", {})
    files_urls: dict[str, str] = {}
    for key, abs_path in files_raw.items():
        filename = Path(abs_path).name
        files_urls[key] = f"{base}/api/v1/projects/{project_id}/files/{filename}"

    return QuoteFilesResponse(
        project_id=project_id,
        quote_number=quote_num,
        files=files_urls,
    )


# ---------------------------------------------------------------------------
# GET /{project_id}/files/{filename}  — download
# ---------------------------------------------------------------------------

@router.get("/{project_id}/files/{filename}")
async def download_file(
    project_id: str,
    filename: str,
    quote_output_dir: Path = Depends(get_quote_output_dir),
) -> FileResponse:
    """Serve a generated quote file (PDF or Excel)."""
    file_path = quote_output_dir / project_id / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found")

    media_type = (
        "application/pdf" if filename.endswith(".pdf")
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    return FileResponse(str(file_path), media_type=media_type, filename=filename)


# ---------------------------------------------------------------------------
# POST /{project_id}/close
# ---------------------------------------------------------------------------

@router.post("/{project_id}/close", response_model=CloseProjectResponse)
async def close_project(
    project_id: str,
    body: CloseProjectRequest,
    redis: aioredis.Redis = Depends(get_redis),
    training_pipeline: MLTrainingPipeline = Depends(get_training_pipeline),
) -> CloseProjectResponse:
    """
    Register actual costs for a closed project and trigger ML re-training
    if enough new projects have been collected.

    The overhead actual is derived as:
        total_real - labor_real - install_real - transport_real
    """
    state = await _get_state(project_id, redis)
    layer2 = state.get("layer2", {})
    layer3 = state.get("layer3", {})
    metadata = state.get("metadata", {})

    features = _extract_features(layer2, metadata.get("project_params", {}))
    overhead_real = max(0.0, body.total_real - body.labor_real - body.install_real - body.transport_real)

    actuals = {
        "labor_usd": body.labor_real,
        "install_usd": body.install_real,
        "transport_usd": body.transport_real,
        "overhead_usd": overhead_real,
    }

    retrained = training_pipeline.register_closed_project({
        "features": features,
        "actuals": actuals,
    })

    logger.info("Project %s closed — retrained=%s", project_id, retrained)
    return CloseProjectResponse(project_id=project_id, registered=True, retrained=retrained)


# ---------------------------------------------------------------------------
# POST /{project_id}/quote/regenerate
# ---------------------------------------------------------------------------

@router.post("/{project_id}/quote/regenerate", response_model=RegenerateResponse)
async def regenerate_quote(
    project_id: str,
    body: RegenerateRequest,
    request: Request,
    redis: aioredis.Redis = Depends(get_redis),
    config: dict = Depends(get_config),
    quote_output_dir: Path = Depends(get_quote_output_dir),
) -> RegenerateResponse:
    """Re-generate the quote PDF/Excel with updated options."""
    state = await _get_state(project_id, redis)
    _require_done(state)

    layer2 = state.get("layer2", {})
    layer3 = state.get("layer3", {})
    metadata = state.get("metadata", {})

    # Apply precio_override if provided
    if body.precio_override is not None:
        layer3 = {**layer3, "precio_sugerido_usd": body.precio_override}

    from src.agents.quote_generator import QuoteGenerator
    gen = QuoteGenerator(config, output_dir=quote_output_dir / project_id)
    quote_data = {
        "proyecto_id": state.get("project_id", project_id),
        "proyecto_nombre": metadata.get("proyecto_nombre", project_id),
        "cliente": metadata.get("cliente", {}),
        "layer2": layer2,
        "layer3": layer3,
    }
    result = await gen.generate(quote_data)

    # Persist updated layer4 state
    state["layer4"] = result
    await redis.set(f"project:{project_id}", json.dumps(state))

    base = str(request.base_url).rstrip("/")
    files_urls = {
        key: f"{base}/api/v1/projects/{project_id}/files/{Path(p).name}"
        for key, p in result.get("files", {}).items()
    }

    return RegenerateResponse(
        project_id=project_id,
        quote_number=result.get("quote_number", ""),
        files=files_urls,
    )
