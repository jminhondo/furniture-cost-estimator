"""
Labor Cost Agent — Capa 3.

Estimates the cost of skilled-labor hours for fabricating a furniture project.

ToolBelt: LaborRulesTool → MLEstimatorTool → LaborLLMTool

Features
--------
n_piezas            — total cut pieces (sum of component.cantidad)
n_modulos           — number of top-level modules / components
n_puertas           — door count
n_cajones           — drawer count
n_estantes          — shelf count
area_m2             — total surface area in m²
factor_complejidad  — 1.0 (simple) … 2.0 (very complex); derived from mix
tiene_lacado        — 1 if any component has material containing 'lacado', else 0
n_materiales_distintos — number of distinct material_ids in the project
"""

from __future__ import annotations

import logging
from pathlib import Path

from anthropic import AsyncAnthropic

from src.agents.tools.base_tools import (
    AsyncEstimatorTool,
    EstimationResult,
    EstimatorTool,
    ToolBelt,
)
from src.agents.tools.ml_tool import MLEstimatorTool

logger = logging.getLogger(__name__)

FEATURE_NAMES = [
    "n_piezas",
    "n_modulos",
    "n_puertas",
    "n_cajones",
    "n_estantes",
    "area_m2",
    "factor_complejidad",
    "tiene_lacado",
    "n_materiales_distintos",
]

# Default model path (relative to project root)
_DEFAULT_MODEL_PATH = Path(__file__).parent.parent.parent.parent / "models" / "labor_gbr.joblib"


# ---------------------------------------------------------------------------
# Rules tool
# ---------------------------------------------------------------------------

class LaborRulesTool(EstimatorTool):
    """
    Rule-based labor estimate.

    Base rate per piece + surcharges for doors, drawers, lacado, complexity.
    """

    def __init__(self, config: dict) -> None:
        self._cfg = config.get("costos_mano_obra", {})

    def is_available(self) -> bool:
        return True

    def estimate(self, features: dict) -> EstimationResult:
        cfg = self._cfg
        rate_pieza = float(cfg.get("usd_por_pieza", 8.0))
        rate_puerta = float(cfg.get("usd_por_puerta_extra", 12.0))
        rate_cajon = float(cfg.get("usd_por_cajon_extra", 15.0))
        lacado_factor = float(cfg.get("factor_lacado", 1.30))

        n_piezas = float(features.get("n_piezas", 0))
        n_puertas = float(features.get("n_puertas", 0))
        n_cajones = float(features.get("n_cajones", 0))
        tiene_lacado = bool(features.get("tiene_lacado", 0))
        factor_complejidad = float(features.get("factor_complejidad", 1.0))

        base = n_piezas * rate_pieza
        surcharge = n_puertas * rate_puerta + n_cajones * rate_cajon
        total = (base + surcharge) * factor_complejidad
        if tiene_lacado:
            total *= lacado_factor

        return EstimationResult(
            value_usd=round(total, 2),
            confidence=0.72,
            source="rules",
            interval_low=round(total * 0.80, 2),
            interval_high=round(total * 1.25, 2),
            explanation="Labor rules: base×piezas + surcharges × complexity",
        )


# ---------------------------------------------------------------------------
# LLM tool
# ---------------------------------------------------------------------------

class LaborLLMTool(AsyncEstimatorTool):
    """LLM-based labor estimator (last resort)."""

    def __init__(self, config: dict) -> None:
        self._client = AsyncAnthropic()
        self._cfg = config

    def is_available(self) -> bool:
        return True

    async def estimate(self, features: dict) -> EstimationResult:
        prompt = (
            "Eres un experto en costos de fabricación de muebles a medida. "
            "Dado el siguiente resumen del proyecto, estimá el costo de mano de obra "
            "de fabricación en USD. Respondé SOLO con un número entero, sin texto extra.\n\n"
            f"Piezas totales: {features.get('n_piezas')}\n"
            f"Módulos: {features.get('n_modulos')}\n"
            f"Puertas: {features.get('n_puertas')}\n"
            f"Cajones: {features.get('n_cajones')}\n"
            f"Área total m²: {features.get('area_m2')}\n"
            f"Factor complejidad: {features.get('factor_complejidad')}\n"
            f"Tiene lacado: {'Sí' if features.get('tiene_lacado') else 'No'}\n"
        )
        message = await self._client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=16,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip().replace(",", ".")
        value = float(raw)
        return EstimationResult(
            value_usd=round(value, 2),
            confidence=0.65,
            source="llm",
            interval_low=round(value * 0.80, 2),
            interval_high=round(value * 1.25, 2),
            explanation="LLM labor estimate",
        )


# ---------------------------------------------------------------------------
# Agent facade
# ---------------------------------------------------------------------------

class LaborAgent:
    """
    Facade that builds the ToolBelt and exposes ``estimate(features)``.

    Parameters
    ----------
    config:     Pre-loaded config dict (from defaults.yml).
    model_path: Override for the joblib model path (useful in tests).
    use_llm:    Set False to disable LLM escalation (default True).
    """

    def __init__(
        self,
        config: dict,
        model_path: str | Path | None = None,
        use_llm: bool = True,
    ) -> None:
        rules = LaborRulesTool(config)
        ml = MLEstimatorTool(model_path or _DEFAULT_MODEL_PATH)
        llm = LaborLLMTool(config) if use_llm else None
        self._belt = ToolBelt(rules_tool=rules, ml_tool=ml, llm_tool=llm)

    async def estimate(self, features: dict) -> EstimationResult:
        return await self._belt.run(features)
