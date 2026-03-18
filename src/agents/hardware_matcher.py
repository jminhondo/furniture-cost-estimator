"""
Hardware Matcher Agent — Capa 2, paso 3.

Rules engine that decides which hardware (herrajes) each furniture component
requires, consolidates them by herraje_id, and computes costs.

Rules applied
-------------
1. Bisagras (hinges)
   - Applied to: ``puerta`` components
   - Quantity per door is determined by door height (largo_mm):
       ≤ 1000 mm → 2 bisagras
       ≤ 1600 mm → 3 bisagras
       >  1600 mm → 4 bisagras
   - Rules come from ``reglas_herrajes.bisagras_por_puerta`` in defaults.yml

2. Correderas (drawer slides)
   - Applied to: ``cajon_frente`` components (one pair of slides per drawer)
   - Slide length is determined by drawer depth (profundidad):
       Look for a ``cajon_lateral`` that shares the same ``parent`` as the
       ``cajon_frente``; use its largo_mm as the profundidad.
       If not found, use ``reglas_herrajes.profundidad_cajon_default_mm``.
   - Rules from ``reglas_herrajes.correderas_por_cajon``

3. Canto PVC (edge banding)
   - Applied to visible component types listed in ``canto.tipos_que_llevan_canto``
   - Meters per piece = 2 × (largo_mm + ancho_mm) × cantidad / 1000
   - Price from ``canto.precio_usd_ml``
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Component types that need edge banding (overrideable via config)
_DEFAULT_CANTO_TIPOS = {"puerta", "lateral", "techo", "piso", "entrepaño", "cajon_frente"}


class HardwareMatcher:
    """Match furniture components to hardware items and compute total costs."""

    def __init__(self, config: dict) -> None:
        self._config = config
        self._herrajes_cat: dict = config.get("herrajes", {})
        self._reglas: dict = config.get("reglas_herrajes", {})
        self._canto_cfg: dict = config.get("canto", {})
        self._canto_tipos: set[str] = set(
            self._canto_cfg.get("tipos_que_llevan_canto", list(_DEFAULT_CANTO_TIPOS))
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def match(self, componentes: list[dict]) -> dict:
        """
        Analyse *componentes* and return the herrajes section for the BOM.

        Returns::

            {
                "lineas": [{"herraje_id", "nombre", "cantidad",
                            "precio_unitario_usd", "precio_total_usd",
                            "unidad"}, ...],
                "total_herrajes_usd": float,
            }
        """
        accumulator: dict[str, dict] = {}  # herraje_id → aggregated line

        # Build a lookup: parent_id → list of components
        by_parent: dict[str | None, list[dict]] = {}
        for comp in componentes:
            pid = comp.get("parent")
            by_parent.setdefault(pid, []).append(comp)

        # ── Rule 1: Bisagras ─────────────────────────────────────────────
        for comp in componentes:
            if comp.get("tipo_inferido") != "puerta":
                continue
            altura = float(comp.get("dimensiones", {}).get("largo", 0))
            cantidad_puertas = int(comp.get("cantidad", 1))
            bisagras_por_puerta = self._bisagras_for_height(altura)
            total_bisagras = bisagras_por_puerta * cantidad_puertas

            if total_bisagras > 0:
                hid = self._reglas.get("bisagras_por_puerta", [{}])[0].get(
                    "herraje_id", "bisagra_blum_110"
                )
                # Find the correct herraje_id for this height
                for rule in self._reglas.get("bisagras_por_puerta", []):
                    if altura <= rule["max_altura_mm"]:
                        hid = rule["herraje_id"]
                        break
                self._add(accumulator, hid, total_bisagras)

        # ── Rule 2: Correderas ───────────────────────────────────────────
        for comp in componentes:
            if comp.get("tipo_inferido") != "cajon_frente":
                continue
            cantidad_cajones = int(comp.get("cantidad", 1))
            profundidad = self._find_drawer_depth(comp, by_parent)
            hid = self._corredera_for_depth(profundidad)
            # Correderas: one pair per drawer
            self._add(accumulator, hid, cantidad_cajones)

        # ── Rule 3: Canto PVC ────────────────────────────────────────────
        total_ml = 0.0
        for comp in componentes:
            if comp.get("tipo_inferido") not in self._canto_tipos:
                continue
            dims = comp.get("dimensiones", {})
            largo = float(dims.get("largo", 0))
            ancho = float(dims.get("ancho", 0))
            cantidad = int(comp.get("cantidad", 1))
            perimeter_m = 2.0 * (largo + ancho) / 1000.0
            total_ml += perimeter_m * cantidad

        if total_ml > 0:
            precio_ml = float(self._canto_cfg.get("precio_usd_ml", 0.85))
            accumulator["canto_pvc"] = {
                "herraje_id": "canto_pvc",
                "nombre": "Canto PVC 0.4mm",
                "cantidad": round(total_ml, 3),
                "precio_unitario_usd": precio_ml,
                "precio_total_usd": round(total_ml * precio_ml, 2),
                "unidad": "ml",
            }

        lineas = list(accumulator.values())
        total = sum(l["precio_total_usd"] for l in lineas)

        return {
            "lineas": lineas,
            "total_herrajes_usd": round(total, 2),
        }

    # ------------------------------------------------------------------
    # Rule helpers
    # ------------------------------------------------------------------

    def _bisagras_for_height(self, altura_mm: float) -> int:
        """Return the number of hinges required for a door of the given height."""
        rules = self._reglas.get("bisagras_por_puerta", [])
        for rule in sorted(rules, key=lambda r: r["max_altura_mm"]):
            if altura_mm <= rule["max_altura_mm"]:
                return int(rule["cantidad"])
        return 4  # safest fallback

    def _corredera_for_depth(self, profundidad_mm: float) -> str:
        """Return the herraje_id for the appropriate drawer slide."""
        rules = self._reglas.get("correderas_por_cajon", [])
        for rule in sorted(rules, key=lambda r: r["max_profundidad_mm"]):
            if profundidad_mm <= rule["max_profundidad_mm"]:
                return rule["herraje_id"]
        return rules[-1]["herraje_id"] if rules else "corredera_blum_500"

    def _find_drawer_depth(
        self,
        cajon_frente: dict,
        by_parent: dict[str | None, list[dict]],
    ) -> float:
        """
        Find the depth of the drawer containing *cajon_frente*.

        Looks for a ``cajon_lateral`` sibling (same parent).  If found,
        uses its ``largo_mm`` as depth.  Falls back to config default.
        """
        parent_id = cajon_frente.get("parent")
        siblings = by_parent.get(parent_id, [])
        for sibling in siblings:
            if sibling.get("tipo_inferido") == "cajon_lateral":
                return float(sibling.get("dimensiones", {}).get("largo", 0))

        default_depth = float(
            self._reglas.get("profundidad_cajon_default_mm", 500)
        )
        logger.debug(
            "No cajon_lateral found for cajon_frente '%s'; using default depth %.0f mm",
            cajon_frente.get("name", "?"),
            default_depth,
        )
        return default_depth

    # ------------------------------------------------------------------
    # Accumulator helper
    # ------------------------------------------------------------------

    def _add(self, acc: dict, herraje_id: str, cantidad: int | float) -> None:
        """Add *cantidad* units of *herraje_id* to the accumulator."""
        spec = self._herrajes_cat.get(herraje_id)
        if spec is None:
            logger.warning("Unknown herraje_id '%s' — skipping", herraje_id)
            return
        precio = float(spec.get("precio_usd", 0))
        if herraje_id not in acc:
            acc[herraje_id] = {
                "herraje_id": herraje_id,
                "nombre": spec.get("nombre", herraje_id),
                "cantidad": 0,
                "precio_unitario_usd": precio,
                "precio_total_usd": 0.0,
                "unidad": spec.get("unidad", "u"),
            }
        acc[herraje_id]["cantidad"] += int(cantidad)
        acc[herraje_id]["precio_total_usd"] = round(
            acc[herraje_id]["cantidad"] * precio, 2
        )
