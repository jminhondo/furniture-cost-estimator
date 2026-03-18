"""
Layer 2 — BOM Builder.

Orchestrates three agents to convert a Layer-1 canonical JSON (from SKP
Parser or PDF Vision Agent) into the Layer-2 BOM JSON consumed by the
Layer-3 cost engine.

Pipeline
--------
1. MaterialGrouper.group()      — resolve materials, bucket pieces by material_id
2. CutOptimizer.optimize()      — per material group: bin-pack pieces into boards
3. HardwareMatcher.match()      — rules engine: hinges, slides, edge banding

Output schema (docs/schemas.md — Salida Capa 2 → entrada Capa 3)
-----------------------------------------------------------------
{
  "proyecto_id": str,
  "tableros": [
      {"material_id", "tableros_necesarios", "costo_tableros_usd",
       "desperdicio_pct", "plan_de_corte": [...]}
  ],
  "herrajes": {
      "lineas": [...],
      "total_herrajes_usd": float
  },
  "resumen": {
      "total_materiales_usd": float,   # tableros only (herrajes separate)
      "piezas_procesadas": int
  }
}

Config loading
--------------
By default, loads ``configs/defaults.yml`` from the project root (resolved
relative to this file's location).  Pass an explicit path or a pre-loaded
dict via the *config* parameter to override for tests.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from src.agents.cut_optimizer import CutOptimizer
from src.agents.hardware_matcher import HardwareMatcher
from src.agents.material_grouper import MaterialGrouper

logger = logging.getLogger(__name__)

# Default config path: <project_root>/configs/defaults.yml
_DEFAULT_CONFIG = Path(__file__).parent.parent.parent / "configs" / "defaults.yml"


def load_config(path: str | Path | None = None) -> dict:
    """Load the YAML configuration file and return it as a plain dict."""
    cfg_path = Path(path) if path else _DEFAULT_CONFIG
    with cfg_path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


class BOMBuilder:
    """
    Build a Layer-2 BOM JSON from a Layer-1 canonical JSON.

    Parameters
    ----------
    config:
        Pre-loaded config dict, or a filesystem path to a YAML config.
        Defaults to ``configs/defaults.yml``.
    """

    def __init__(self, config: dict | str | Path | None = None) -> None:
        if isinstance(config, dict):
            cfg = config
        else:
            cfg = load_config(config)

        self._config = cfg
        self.material_grouper = MaterialGrouper(cfg)
        self.cut_optimizer = CutOptimizer(cfg)
        self.hardware_matcher = HardwareMatcher(cfg)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self, layer1_json: dict) -> dict:
        """
        Convert Layer-1 JSON to Layer-2 BOM JSON.

        Parameters
        ----------
        layer1_json:
            Output of SKPParserAgent.parse() or PDFVisionAgent.parse().

        Returns
        -------
        dict matching the Layer-2 canonical schema.
        """
        proyecto_id: str = layer1_json.get("proyecto_id", "")
        componentes: list[dict] = layer1_json.get("componentes", [])

        logger.info(
            "BOM build started — proyecto='%s', %d components",
            proyecto_id, len(componentes),
        )

        # ── Step 1: Material grouping ────────────────────────────────────
        groups = self.material_grouper.group(componentes)
        logger.debug("Material groups: %s", [g.material_id for g in groups])

        # ── Step 2: Cut optimisation (one result per material group) ─────
        tableros: list[dict] = []
        total_tableros_usd = 0.0

        for group in groups:
            if not group.piezas:
                continue
            result = self.cut_optimizer.optimize(group)
            tableros.append(result)
            total_tableros_usd += result["costo_tableros_usd"]
            logger.debug(
                "Cut plan '%s': %d boards, waste=%.1f%%",
                group.material_id,
                result["tableros_necesarios"],
                result["desperdicio_pct"] * 100,
            )

        # ── Step 3: Hardware matching ────────────────────────────────────
        herrajes = self.hardware_matcher.match(componentes)
        logger.debug(
            "Hardware: %d line(s), total USD %.2f",
            len(herrajes["lineas"]),
            herrajes["total_herrajes_usd"],
        )

        return {
            "proyecto_id": proyecto_id,
            "tableros": tableros,
            "herrajes": herrajes,
            "resumen": {
                "total_materiales_usd": round(total_tableros_usd, 2),
                "piezas_procesadas": len(componentes),
            },
        }
