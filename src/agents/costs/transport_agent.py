"""
Transport Cost Agent — Capa 3.

Estimates the cost of transporting finished furniture to the job site and
materials from the supplier to the workshop.

ToolBelt: TransportRulesTool → MLEstimatorTool   (no LLM for this agent)

Features
--------
n_piezas              — total cut pieces
area_m2               — total surface area in m²
volumen_m3            — estimated packed volume in m³
distancia_obra_km     — workshop → job site distance (km)
distancia_proveedor_km— supplier → workshop distance (km)
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
    "volumen_m3",
    "distancia_obra_km",
    "distancia_proveedor_km",
]

_DEFAULT_MODEL_PATH = (
    Path(__file__).parent.parent.parent.parent / "models" / "transport_gbr.joblib"
)


class TransportRulesTool(EstimatorTool):
    """Rule-based transport estimate."""

    def __init__(self, config: dict) -> None:
        self._cfg = config.get("costos_transporte", {})

    def is_available(self) -> bool:
        return True

    def estimate(self, features: dict) -> EstimationResult:
        cfg = self._cfg
        rate_km_obra = float(cfg.get("usd_por_km_obra", 1.20))
        rate_km_proveedor = float(cfg.get("usd_por_km_proveedor", 0.60))
        base_carga = float(cfg.get("usd_base_carga", 20.0))
        rate_m3 = float(cfg.get("usd_por_m3", 15.0))

        distancia_obra = float(features.get("distancia_obra_km", 0))
        distancia_proveedor = float(features.get("distancia_proveedor_km", 0))
        volumen_m3 = float(features.get("volumen_m3", 0))

        # Delivery: round-trip to job site
        costo_obra = distancia_obra * rate_km_obra * 2
        # Material pickup: one-way from supplier
        costo_proveedor = distancia_proveedor * rate_km_proveedor
        # Volume-based loading surcharge
        costo_volumen = base_carga + volumen_m3 * rate_m3
        total = costo_obra + costo_proveedor + costo_volumen

        return EstimationResult(
            value_usd=round(total, 2),
            confidence=0.75,
            source="rules",
            interval_low=round(total * 0.85, 2),
            interval_high=round(total * 1.20, 2),
            explanation="Transport rules: delivery + pickup + volume surcharge",
        )


class TransportAgent:
    """Facade for the transport cost ToolBelt (Rules + ML, no LLM)."""

    def __init__(
        self,
        config: dict,
        model_path: str | Path | None = None,
    ) -> None:
        rules = TransportRulesTool(config)
        ml = MLEstimatorTool(model_path or _DEFAULT_MODEL_PATH)
        self._belt = ToolBelt(rules_tool=rules, ml_tool=ml, llm_tool=None)

    async def estimate(self, features: dict) -> EstimationResult:
        return await self._belt.run(features)
