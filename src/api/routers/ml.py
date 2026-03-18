"""
ML router — model status and manual retraining.

GET  /api/v1/ml/status   — check training state for each cost agent
POST /api/v1/ml/retrain  — manually trigger retraining (if ≥ min_samples)
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends

from src.api.deps import get_training_pipeline
from src.api.schemas import AgentMLStatus, MLRetrainResponse, MLStatusResponse
from src.agents.tools.training_pipeline import MLTrainingPipeline, _AGENTS, _DEFAULT_MODELS_DIR

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ml", tags=["ml"])


def _agent_status(agent_name: str, models_dir: Path) -> AgentMLStatus:
    """Read model artifact metadata from disk without loading the model."""
    model_path = models_dir / f"{agent_name}_gbr.joblib"
    n_samples = 0

    if model_path.exists():
        try:
            import joblib
            artifact = joblib.load(model_path)
            n_samples = int(artifact.get("n_samples", 0))
        except Exception:
            pass

    return AgentMLStatus(
        model_exists=model_path.exists(),
        n_samples=n_samples,
        model_path=str(model_path),
    )


@router.get("/status", response_model=MLStatusResponse)
async def ml_status(
    training_pipeline: MLTrainingPipeline = Depends(get_training_pipeline),
) -> MLStatusResponse:
    """Return training status for each cost agent (labor, install, transport, overhead)."""
    models_dir = training_pipeline._models_dir
    agents = {
        name: _agent_status(name, models_dir)
        for name, _ in _AGENTS
    }
    return MLStatusResponse(agents=agents)


@router.post("/retrain", response_model=MLRetrainResponse)
async def ml_retrain(
    training_pipeline: MLTrainingPipeline = Depends(get_training_pipeline),
) -> MLRetrainResponse:
    """
    Manually trigger a retraining pass over all collected data.

    Returns immediately; reports whether retraining was possible
    (requires ≥ 2 samples per agent).
    """
    all_data = training_pipeline._all_data
    if not all_data:
        return MLRetrainResponse(
            triggered=False,
            message="No training data registered yet. Close at least one project first.",
        )

    try:
        training_pipeline._retrain_all()
        return MLRetrainResponse(
            triggered=True,
            message=f"Retraining completed on {len(all_data)} projects.",
        )
    except Exception as exc:
        logger.exception("Manual retraining failed")
        return MLRetrainResponse(triggered=False, message=str(exc))
