"""
Layer 3 — Cost Engine.

Orchestrates four cost agents in parallel to produce a full cost breakdown
from a Layer-2 BOM JSON.

Pipeline
--------
1. Feature extraction from Layer-2 JSON + project_params
2. asyncio.gather(): LaborAgent, InstallAgent, TransportAgent, OverheadAgent
3. Consolidate results → Layer-3 schema JSON

Output schema (docs/schemas.md — Salida Capa 3)
-------------------------------------------------
{
  "proyecto_id": str,
  "costo_materiales_usd": float,     # tableros + herrajes
  "costo_mano_obra_usd": float,
  "costo_instalacion_usd": float,
  "costo_transporte_usd": float,
  "costo_indirecto_usd": float,      # overhead
  "costo_directo_usd": float,        # materiales + labor + install + transport
  "costo_total_usd": float,          # directo + overhead
  "precio_sugerido_usd": float,      # total × (1 + margen) × (1 + iva)
  "confianza_global": float,         # weighted average confidence
  "fuentes": {
      "materiales": "bom",
      "mano_obra": str,              # "rules" | "ml" | "blend" | "llm"
      "instalacion": str,
      "transporte": str,
      "indirecto": str,
  },
  "intervalos": {
      "labor_low": float, "labor_high": float,
      "install_low": float, "install_high": float,
      "transport_low": float, "transport_high": float,
      "overhead_low": float, "overhead_high": float,
  },
}

Config loading
--------------
By default, loads ``configs/defaults.yml`` from the project root.
Pass an explicit path or a pre-loaded dict via the *config* parameter.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import yaml

from src.agents.costs.install_agent import InstallAgent
from src.agents.costs.labor_agent import LaborAgent
from src.agents.costs.overhead_agent import OverheadAgent
from src.agents.costs.transport_agent import TransportAgent
from src.agents.tools.base_tools import EstimationResult

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG = Path(__file__).parent.parent.parent / "configs" / "defaults.yml"


def load_config(path: str | Path | None = None) -> dict:
    """Load the YAML configuration file and return it as a plain dict."""
    cfg_path = Path(path) if path else _DEFAULT_CONFIG
    with cfg_path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------

def _extract_features(layer2_json: dict, project_params: dict) -> dict:
    """
    Derive cost-agent features from Layer-2 BOM and project parameters.

    Parameters
    ----------
    layer2_json:
        Output of BOMBuilder.build().
    project_params:
        Caller-supplied dict with project-level parameters:
            distancia_obra_km, distancia_proveedor_km, n_instaladores,
            tipo_obra, duracion_proyecto_dias, tiene_lacado (bool)
    """
    tableros: list[dict] = layer2_json.get("tableros", [])
    herrajes: dict = layer2_json.get("herrajes", {})

    # ── Count pieces from cut plans ──────────────────────────────────────
    n_piezas = 0
    area_m2 = 0.0
    volumen_m3 = 0.0
    n_puertas = 0
    n_cajones = 0
    n_estantes = 0

    for tablero in tableros:
        for corte in tablero.get("plan_de_corte", []):
            n_piezas += 1
            largo_m = corte.get("largo_mm", 0) / 1000.0
            ancho_m = corte.get("ancho_mm", 0) / 1000.0
            area_m2 += largo_m * ancho_m
            # Assume average thickness of 18mm for volume estimate
            volumen_m3 += largo_m * ancho_m * 0.018

    # ── Count hardware for door/drawer detection ─────────────────────────
    for linea in herrajes.get("lineas", []):
        hid = linea.get("herraje_id", "")
        qty = int(linea.get("cantidad", 0))
        if "bisagra" in hid:
            # Each door has 2–4 bisagras; approximate door count
            n_puertas += max(1, qty // 2)
        elif "corredera" in hid:
            n_cajones += qty

    # ── Module count = number of distinct tablero materials ──────────────
    n_modulos = len(tableros) if tableros else 1

    # ── Complexity factor ─────────────────────────────────────────────────
    # 1.0 base + 0.1 per door + 0.15 per drawer, capped at 2.0
    factor_complejidad = min(2.0, 1.0 + n_puertas * 0.10 + n_cajones * 0.15)

    # ── Material count ───────────────────────────────────────────────────
    n_materiales_distintos = len(tableros)

    return {
        "n_piezas": n_piezas,
        "n_modulos": n_modulos,
        "n_puertas": n_puertas,
        "n_cajones": n_cajones,
        "n_estantes": n_estantes,
        "area_m2": round(area_m2, 3),
        "volumen_m3": round(volumen_m3, 4),
        "factor_complejidad": round(factor_complejidad, 2),
        "tiene_lacado": int(bool(project_params.get("tiene_lacado", False))),
        "n_materiales_distintos": n_materiales_distintos,
        "distancia_obra_km": float(project_params.get("distancia_obra_km", 0)),
        "distancia_proveedor_km": float(project_params.get("distancia_proveedor_km", 0)),
        "n_instaladores": float(project_params.get("n_instaladores", 2)),
        "tipo_obra": int(project_params.get("tipo_obra", 0)),
        "duracion_proyecto_dias": float(project_params.get("duracion_proyecto_dias", 5)),
    }


# ---------------------------------------------------------------------------
# CostEngine
# ---------------------------------------------------------------------------

class CostEngine:
    """
    Build the Layer-3 cost breakdown from a Layer-2 BOM JSON.

    Parameters
    ----------
    config:
        Pre-loaded config dict, or a filesystem path to a YAML config.
        Defaults to ``configs/defaults.yml``.
    use_llm:
        Whether to allow LLM escalation in Labor and Install agents.
        Default True; set False in tests / offline environments.
    """

    def __init__(
        self,
        config: dict | str | Path | None = None,
        use_llm: bool = True,
    ) -> None:
        if isinstance(config, dict):
            cfg = config
        else:
            cfg = load_config(config)

        self._config = cfg
        self._margen: float = float(cfg.get("precio", {}).get("margen_default", 0.32))
        self._iva: float = float(cfg.get("precio", {}).get("iva_pct", 0.21))

        self._labor = LaborAgent(cfg, use_llm=use_llm)
        self._install = InstallAgent(cfg, use_llm=use_llm)
        self._transport = TransportAgent(cfg)
        self._overhead = OverheadAgent(cfg)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def estimate(
        self,
        layer2_json: dict,
        project_params: dict | None = None,
    ) -> dict:
        """
        Produce Layer-3 cost breakdown JSON.

        Parameters
        ----------
        layer2_json:
            Output of BOMBuilder.build().
        project_params:
            Optional project-level parameters (see _extract_features).
        """
        params = project_params or {}
        proyecto_id: str = layer2_json.get("proyecto_id", "")

        logger.info("CostEngine.estimate — proyecto='%s'", proyecto_id)

        # ── Material costs from BOM (already computed) ────────────────────
        resumen = layer2_json.get("resumen", {})
        herrajes = layer2_json.get("herrajes", {})
        costo_materiales = (
            float(resumen.get("total_materiales_usd", 0))
            + float(herrajes.get("total_herrajes_usd", 0))
        )

        # ── Feature extraction ────────────────────────────────────────────
        features = _extract_features(layer2_json, params)

        # ── Run four agents in parallel ───────────────────────────────────
        labor_r, install_r, transport_r = await asyncio.gather(
            self._labor.estimate(features),
            self._install.estimate(features),
            self._transport.estimate(features),
        )

        # Overhead needs direct cost → run sequentially after the above
        costo_directo_pre = (
            costo_materiales
            + labor_r.value_usd
            + install_r.value_usd
            + transport_r.value_usd
        )
        overhead_features = {**features, "costo_directo_usd": costo_directo_pre}
        overhead_r: EstimationResult = await self._overhead.estimate(overhead_features)

        # ── Consolidate ───────────────────────────────────────────────────
        costo_directo = costo_directo_pre
        costo_total = costo_directo + overhead_r.value_usd
        precio_sugerido = costo_total * (1 + self._margen) * (1 + self._iva)

        # Weighted confidence (materiales weight = 0.35, the four agents share 0.65)
        confianza_global = (
            0.35 * 1.0  # BOM cost is deterministic
            + 0.20 * labor_r.confidence
            + 0.15 * install_r.confidence
            + 0.15 * transport_r.confidence
            + 0.15 * overhead_r.confidence
        )

        logger.info(
            "CostEngine done — total=%.2f, precio=%.2f, conf=%.2f",
            costo_total, precio_sugerido, confianza_global,
        )

        return {
            "proyecto_id": proyecto_id,
            "costo_materiales_usd": round(costo_materiales, 2),
            "costo_mano_obra_usd": labor_r.value_usd,
            "costo_instalacion_usd": install_r.value_usd,
            "costo_transporte_usd": transport_r.value_usd,
            "costo_indirecto_usd": overhead_r.value_usd,
            "costo_directo_usd": round(costo_directo, 2),
            "costo_total_usd": round(costo_total, 2),
            "precio_sugerido_usd": round(precio_sugerido, 2),
            "confianza_global": round(confianza_global, 4),
            "fuentes": {
                "materiales": "bom",
                "mano_obra": labor_r.source,
                "instalacion": install_r.source,
                "transporte": transport_r.source,
                "indirecto": overhead_r.source,
            },
            "intervalos": {
                "labor_low": labor_r.interval_low,
                "labor_high": labor_r.interval_high,
                "install_low": install_r.interval_low,
                "install_high": install_r.interval_high,
                "transport_low": transport_r.interval_low,
                "transport_high": transport_r.interval_high,
                "overhead_low": overhead_r.interval_low,
                "overhead_high": overhead_r.interval_high,
            },
        }
