"""
Cut Optimizer Agent — Capa 2, paso 2.

Given a MaterialGroup (pieces to cut from the same sheet material), packs
them into the minimum number of standard-size boards using 2-D bin packing.

Algorithm choices
-----------------
- rectpack, PackingMode.Offline + SORT_AREA  (fits large pieces first)
- rotation=True  (pieces can be rotated 90°)
- Guillotine algorithm via rectpack.newPacker defaults
- Unlimited bins (count=inf): packer keeps adding sheets until all pieces fit.

Kerf handling
-------------
Each piece expands by kerf_mm in both dimensions before packing to reserve
the width lost by the saw blade.  The plan_de_corte records the actual piece
dimensions (without kerf).

Output per MaterialGroup
------------------------
{
  "material_id": str,
  "tableros_necesarios": int,
  "costo_tableros_usd": float,
  "desperdicio_pct": float,          # (sheet_area - piece_area) / sheet_area
  "plan_de_corte": [
      {"pieza_id", "nombre", "tablero_num", "x_mm", "y_mm",
       "largo_mm", "ancho_mm", "rotada": bool}, ...
  ]
}
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import rectpack

from src.agents.material_grouper import MaterialGroup

logger = logging.getLogger(__name__)


@dataclass
class CutEntry:
    pieza_id: str
    nombre: str
    tablero_num: int
    x_mm: float
    y_mm: float
    largo_mm: float
    ancho_mm: float
    rotada: bool


class CutOptimizer:
    """Pack pieces into standard-size boards, minimising the number of boards."""

    def __init__(self, config: dict) -> None:
        self._kerf: int = int(config.get("corte", {}).get("kerf_mm", 3))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def optimize(self, group: MaterialGroup) -> dict:
        """
        Pack all pieces in *group* and return the cut-plan dict for Layer 2.

        Pieces with cantidad > 1 are expanded: each unit is added as a
        separate rectangle to the packer.
        """
        spec = group.spec
        sheet_w = int(spec.hoja_largo_mm)
        sheet_h = int(spec.hoja_ancho_mm)
        kerf = self._kerf

        # ── Build packer ────────────────────────────────────────────────
        packer = rectpack.newPacker(
            mode=rectpack.PackingMode.Offline,
            sort_algo=rectpack.SORT_AREA,
            rotation=True,
        )
        # Unlimited bins — packer adds sheets until all pieces fit
        packer.add_bin(sheet_w, sheet_h, count=float("inf"))

        # ── Expand pieces by quantity and register with packer ──────────
        rid = 0
        rid_map: dict[int, dict] = {}

        for pieza in group.piezas:
            dims = pieza.get("dimensiones", {})
            largo = float(dims.get("largo", 0))
            ancho = float(dims.get("ancho", 0))
            cantidad = int(pieza.get("cantidad", 1))

            if largo <= 0 or ancho <= 0:
                logger.warning("Pieza '%s' has zero dimension, skipping", pieza.get("name", "?"))
                continue

            if largo + kerf > sheet_w and ancho + kerf > sheet_h:
                logger.warning(
                    "Pieza '%s' (%.0f×%.0f) exceeds sheet size (%.0f×%.0f)",
                    pieza.get("name"), largo, ancho, sheet_w, sheet_h,
                )

            for _ in range(cantidad):
                # Add kerf to both dimensions — reserves saw-blade width
                pack_w = int(largo) + kerf
                pack_h = int(ancho) + kerf
                packer.add_rect(pack_w, pack_h, rid=rid)
                rid_map[rid] = {
                    "pieza_id": pieza.get("id", ""),
                    "nombre": pieza.get("name", ""),
                    "orig_w": pack_w,  # used to detect rotation
                    "largo_mm": largo,
                    "ancho_mm": ancho,
                }
                rid += 1

        packer.pack()

        # ── Build plan_de_corte ─────────────────────────────────────────
        plan: list[CutEntry] = []
        bins_used = 0
        for bin_idx, bin_ in enumerate(packer):
            bins_used = bin_idx + 1
            for rect in bin_:
                info = rid_map[rect.rid]
                rotada = rect.width != info["orig_w"]
                plan.append(
                    CutEntry(
                        pieza_id=info["pieza_id"],
                        nombre=info["nombre"],
                        tablero_num=bin_idx,
                        x_mm=float(rect.x),
                        y_mm=float(rect.y),
                        # Record actual placed dimensions (without kerf)
                        largo_mm=float(rect.width - kerf),
                        ancho_mm=float(rect.height - kerf),
                        rotada=rotada,
                    )
                )

        # ── Costs and waste ─────────────────────────────────────────────
        tableros_necesarios = bins_used
        sheet_area_mm2 = float(sheet_w) * float(sheet_h)
        total_sheet_area = tableros_necesarios * sheet_area_mm2

        total_piece_area = sum(
            float(p.get("dimensiones", {}).get("largo", 0))
            * float(p.get("dimensiones", {}).get("ancho", 0))
            * int(p.get("cantidad", 1))
            for p in group.piezas
        )

        desperdicio_pct = (
            (total_sheet_area - total_piece_area) / total_sheet_area
            if total_sheet_area > 0
            else 0.0
        )

        # Cost = price per m² × sheet area × number of sheets
        precio_m2 = spec.precio_usd_m2
        costo_tableros_usd = tableros_necesarios * (sheet_area_mm2 / 1_000_000) * precio_m2

        return {
            "material_id": group.material_id,
            "tableros_necesarios": tableros_necesarios,
            "costo_tableros_usd": round(costo_tableros_usd, 2),
            "desperdicio_pct": round(desperdicio_pct, 4),
            "plan_de_corte": [
                {
                    "pieza_id": e.pieza_id,
                    "nombre": e.nombre,
                    "tablero_num": e.tablero_num,
                    "x_mm": e.x_mm,
                    "y_mm": e.y_mm,
                    "largo_mm": e.largo_mm,
                    "ancho_mm": e.ancho_mm,
                    "rotada": e.rotada,
                }
                for e in plan
            ],
        }
