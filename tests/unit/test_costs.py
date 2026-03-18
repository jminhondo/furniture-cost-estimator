"""
Unit tests for the Layer-3 ToolBelt pattern and CostEngine.

Tests
-----
1. test_rules_tool_always_available         — LaborRulesTool.is_available() == True
2. test_ml_tool_not_available_below_min_samples — MLEstimatorTool unavailable w/o model
3. test_toolbelt_uses_ml_when_confident     — ML confident → blend result
4. test_toolbelt_falls_back_to_llm          — ML unavailable, rules low conf → LLM
5. test_toolbelt_blends_ml_and_rules        — blend weights and value check
6. test_training_pipeline_retrains_after_n_projects — register N projects → retrain
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from src.agents.costs.labor_agent import LaborRulesTool
from src.agents.tools.base_tools import (
    EstimationResult,
    EstimatorTool,
    AsyncEstimatorTool,
    ToolBelt,
    ML_WEIGHT,
    RULES_WEIGHT,
)
from src.agents.tools.ml_tool import MLEstimatorTool, _confidence_for_samples
from src.agents.tools.training_pipeline import MLTrainingPipeline, RETRAIN_EVERY_N

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MINIMAL_CONFIG: dict = {
    "costos_mano_obra": {
        "usd_por_pieza": 8.0,
        "usd_por_puerta_extra": 12.0,
        "usd_por_cajon_extra": 15.0,
        "factor_lacado": 1.30,
    }
}

_FEATURES: dict = {
    "n_piezas": 20,
    "n_modulos": 4,
    "n_puertas": 4,
    "n_cajones": 2,
    "n_estantes": 3,
    "area_m2": 8.5,
    "factor_complejidad": 1.3,
    "tiene_lacado": 0,
    "n_materiales_distintos": 2,
}


def _make_result(value: float, confidence: float, source: str = "rules") -> EstimationResult:
    return EstimationResult(
        value_usd=value,
        confidence=confidence,
        source=source,
        interval_low=value * 0.85,
        interval_high=value * 1.15,
    )


# ---------------------------------------------------------------------------
# Test 1 — Rules tool always available
# ---------------------------------------------------------------------------

def test_rules_tool_always_available():
    tool = LaborRulesTool(_MINIMAL_CONFIG)
    assert tool.is_available() is True

    result = tool.estimate(_FEATURES)
    assert result.source == "rules"
    assert result.value_usd > 0
    assert 0.0 < result.confidence <= 1.0


# ---------------------------------------------------------------------------
# Test 2 — ML tool unavailable without a model file
# ---------------------------------------------------------------------------

def test_ml_tool_not_available_below_min_samples(tmp_path):
    non_existent = tmp_path / "no_model.joblib"
    tool = MLEstimatorTool(non_existent, min_samples_to_activate=5)
    assert tool.is_available() is False


# ---------------------------------------------------------------------------
# Test 3 — ToolBelt uses ML (blend) when ML is confident
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_toolbelt_uses_ml_when_confident():
    rules_tool = MagicMock(spec=EstimatorTool)
    rules_tool.is_available.return_value = True
    rules_tool.estimate.return_value = _make_result(200.0, 0.72, "rules")

    ml_tool = MagicMock(spec=EstimatorTool)
    ml_tool.is_available.return_value = True
    ml_tool.estimate.return_value = _make_result(250.0, 0.85, "ml")

    belt = ToolBelt(rules_tool=rules_tool, ml_tool=ml_tool)
    result = await belt.run(_FEATURES)

    assert result.source == "blend"
    expected_value = ML_WEIGHT * 250.0 + RULES_WEIGHT * 200.0
    assert abs(result.value_usd - expected_value) < 0.02


# ---------------------------------------------------------------------------
# Test 4 — ToolBelt falls back to LLM when rules confidence is low
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_toolbelt_falls_back_to_llm():
    rules_tool = MagicMock(spec=EstimatorTool)
    rules_tool.is_available.return_value = True
    rules_tool.estimate.return_value = _make_result(180.0, 0.40, "rules")  # below threshold

    ml_tool = MagicMock(spec=EstimatorTool)
    ml_tool.is_available.return_value = False  # ML not ready

    llm_tool = MagicMock(spec=AsyncEstimatorTool)
    llm_tool.is_available.return_value = True
    llm_tool.estimate = AsyncMock(return_value=_make_result(210.0, 0.65, "llm"))

    belt = ToolBelt(rules_tool=rules_tool, ml_tool=ml_tool, llm_tool=llm_tool)
    result = await belt.run(_FEATURES)

    assert result.source == "llm"
    assert result.value_usd == 210.0
    llm_tool.estimate.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test 5 — Blend weights produce correct weighted average
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_toolbelt_blends_ml_and_rules():
    rules_tool = MagicMock(spec=EstimatorTool)
    rules_tool.is_available.return_value = True
    rules_result = _make_result(100.0, 0.72, "rules")
    rules_tool.estimate.return_value = rules_result

    ml_tool = MagicMock(spec=EstimatorTool)
    ml_tool.is_available.return_value = True
    ml_result = _make_result(140.0, 0.85, "ml")
    ml_tool.estimate.return_value = ml_result

    belt = ToolBelt(rules_tool=rules_tool, ml_tool=ml_tool)
    result = await belt.run(_FEATURES)

    expected_value = ML_WEIGHT * 140.0 + RULES_WEIGHT * 100.0  # 128.0
    expected_conf = ML_WEIGHT * 0.85 + RULES_WEIGHT * 0.72    # 0.811

    assert result.source == "blend"
    assert abs(result.value_usd - expected_value) < 0.02
    assert abs(result.confidence - expected_conf) < 0.001


# ---------------------------------------------------------------------------
# Test 6 — Training pipeline retrains after N projects
# ---------------------------------------------------------------------------

def test_training_pipeline_retrains_after_n_projects(tmp_path):
    pipeline = MLTrainingPipeline(
        models_dir=tmp_path,
        retrain_every_n=RETRAIN_EVERY_N,
    )

    project_template = {
        "features": {**_FEATURES, "costo_directo_usd": 1000.0, "duracion_proyecto_dias": 7,
                     "volumen_m3": 0.5, "distancia_obra_km": 20.0,
                     "distancia_proveedor_km": 10.0, "n_instaladores": 2, "tipo_obra": 0},
        "actuals": {
            "labor_usd": 350.0,
            "install_usd": 120.0,
            "transport_usd": 80.0,
            "overhead_usd": 180.0,
        },
    }

    retrain_triggered = False
    for i in range(RETRAIN_EVERY_N):
        triggered = pipeline.register_closed_project(project_template)
        if triggered:
            retrain_triggered = True

    assert retrain_triggered, "Pipeline should have triggered retraining"

    # Verify model artifacts were created for at least one agent
    artifacts = list(tmp_path.glob("*.joblib"))
    assert len(artifacts) > 0, "At least one model artifact should exist"


# ---------------------------------------------------------------------------
# Confidence scaling
# ---------------------------------------------------------------------------

def test_confidence_scaling():
    assert _confidence_for_samples(0) == 0.0
    assert _confidence_for_samples(1) > 0.0
    # Plateau at 0.92
    assert _confidence_for_samples(10_000) < 0.92 + 1e-6
    # Monotonically increasing
    prev = 0.0
    for n in [1, 5, 10, 30, 60, 100, 200]:
        conf = _confidence_for_samples(n)
        assert conf > prev
        prev = conf
