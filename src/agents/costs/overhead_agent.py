"""
Overhead Cost Agent — Capa 3.

Estimates indirect costs (overhead) as a percentage of direct costs, with
adjustments for project size and duration.

ToolBelt: OverheadRulesTool → MLEstimatorTool   (no LLM for this agent)

Features
--------
n_piezas            — total cut pieces
area_m2             — total surface area in m²
costo_directo_usd   — sum of tableros + herrajes + labor + install + transport
duracion_proyecto_dias — estimated project duration in working days
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.agents.tools.base_tools import (
    EstimationResult,
    EstimatorTool,
    ToolBelt,
)
from src.agents.tools.ml_tool import MLEstimatorTool

logger = logging.getLogger(__name__)

FEATURE_NAMES = [
    "n_piezas",
    "area_m2",
    "costo_directo_usd",
    "duracion_proyecto_dias",
]

_DEFAULT_MODEL_PATH = (
    Path(__file__).parent.parent.parent.parent / "models" / "overhead_gbr.joblib"
)


class OverheadRulesTool(EstimatorTool):
    """
    Percentage-based overhead estimate.

    overhead = costo_directo × overhead_pct × duration_factor
    where duration_factor = 1 + (duracion_dias - 5) × 0.01  (capped at 1.30)
    """

    def __init__(self, config: dict) -> None:
        self._overhead_pct: float = float(
            config.get("costos_indirectos", {}).get("overhead_pct", 0.18)
        )

    def is_available(self) -> bool:
        return True

    def estimate(self, features: dict) -> EstimationResult:
        costo_directo = float(features.get("costo_directo_usd", 0))
        duracion_dias = float(features.get("duracion_proyecto_dias", 5))

        # Longer projects accumulate more overhead
        duration_factor = min(1.30, 1.0 + max(0, duracion_dias - 5) * 0.01)
        total = costo_directo * self._overhead_pct * duration_factor

        return EstimationResult(
            value_usd=round(total, 2),
            confidence=0.80,
            source="rules",
            interval_low=round(total * 0.90, 2),
            interval_high=round(total * 1.15, 2),
            explanation=(
                f"Overhead {self._overhead_pct*100:.0f}% of direct costs "
                f"× duration_factor={duration_factor:.2f}"
            ),
        )


class OverheadAgent:
    """Facade for the overhead cost ToolBelt (Rules + ML, no LLM)."""

    def __init__(
        self,
        config: dict,
        model_path: str | Path | None = None,
    ) -> None:
        rules = OverheadRulesTool(config)
        ml = MLEstimatorTool(model_path or _DEFAULT_MODEL_PATH)
        self._belt = ToolBelt(rules_tool=rules, ml_tool=ml, llm_tool=None)

    async def estimate(self, features: dict) -> EstimationResult:
        return await self._belt.run(features)
