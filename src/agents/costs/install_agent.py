"""
Install Cost Agent — Capa 3.

Estimates the cost of on-site installation labor.

ToolBelt: InstallRulesTool → MLEstimatorTool → InstallLLMTool

Features
--------
(all labor features) +
distancia_obra_km   — distance from workshop to job site in km
n_instaladores      — expected number of installers
tipo_obra           — 0=residencial, 1=comercial, 2=oficina (int-encoded)
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
    "distancia_obra_km",
    "n_instaladores",
    "tipo_obra",
]

_DEFAULT_MODEL_PATH = (
    Path(__file__).parent.parent.parent.parent / "models" / "install_gbr.joblib"
)

_TIPO_OBRA_FACTOR = {0: 1.0, 1: 1.20, 2: 1.15}  # residencial / comercial / oficina


class InstallRulesTool(EstimatorTool):
    """Rule-based installation estimate."""

    def __init__(self, config: dict) -> None:
        self._cfg = config.get("costos_instalacion", {})

    def is_available(self) -> bool:
        return True

    def estimate(self, features: dict) -> EstimationResult:
        cfg = self._cfg
        rate_modulo = float(cfg.get("usd_por_modulo", 25.0))
        rate_km = float(cfg.get("usd_por_km", 0.80))

        n_modulos = float(features.get("n_modulos", 0))
        n_instaladores = float(features.get("n_instaladores", 2))
        distancia_km = float(features.get("distancia_obra_km", 0))
        tipo_obra = int(features.get("tipo_obra", 0))
        factor_complejidad = float(features.get("factor_complejidad", 1.0))

        tipo_factor = _TIPO_OBRA_FACTOR.get(tipo_obra, 1.0)
        travel = distancia_km * rate_km * 2  # round-trip
        labor = n_modulos * rate_modulo * n_instaladores * tipo_factor * factor_complejidad
        total = labor + travel

        return EstimationResult(
            value_usd=round(total, 2),
            confidence=0.70,
            source="rules",
            interval_low=round(total * 0.80, 2),
            interval_high=round(total * 1.30, 2),
            explanation="Install rules: modules×rate×installers + travel",
        )


class InstallLLMTool(AsyncEstimatorTool):
    """LLM-based installation estimator (last resort)."""

    def __init__(self, config: dict) -> None:
        self._client = AsyncAnthropic()
        self._cfg = config

    def is_available(self) -> bool:
        return True

    async def estimate(self, features: dict) -> EstimationResult:
        prompt = (
            "Eres un experto en instalación de muebles a medida. "
            "Estimá el costo de instalación en USD. Respondé SOLO con un número.\n\n"
            f"Módulos: {features.get('n_modulos')}\n"
            f"Instaladores: {features.get('n_instaladores')}\n"
            f"Distancia km: {features.get('distancia_obra_km')}\n"
            f"Tipo obra: {features.get('tipo_obra')} (0=residencial,1=comercial,2=oficina)\n"
            f"Factor complejidad: {features.get('factor_complejidad')}\n"
        )
        message = await self._client.messages.create(
            model="claude-haiku-4-5-20251001",
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
            interval_high=round(value * 1.30, 2),
            explanation="LLM install estimate",
        )


class InstallAgent:
    """Facade for the installation cost ToolBelt."""

    def __init__(
        self,
        config: dict,
        model_path: str | Path | None = None,
        use_llm: bool = True,
    ) -> None:
        rules = InstallRulesTool(config)
        ml = MLEstimatorTool(model_path or _DEFAULT_MODEL_PATH)
        llm = InstallLLMTool(config) if use_llm else None
        self._belt = ToolBelt(rules_tool=rules, ml_tool=ml, llm_tool=llm)

    async def estimate(self, features: dict) -> EstimationResult:
        return await self._belt.run(features)
