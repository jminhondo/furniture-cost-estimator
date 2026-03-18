"""
Material Grouper Agent — Capa 2, paso 1.

Responsibilities
----------------
1. resolve_material(): map a free-text material name + espesor to a catalog
   MaterialSpec from configs/defaults.yml.
   Strategy:
     a) exact alias match (case-insensitive, stripped) — if multiple candidates,
        pick the one whose espesor_mm is closest to the component's espesor.
     b) espesor-only match (within ±2 mm) when no alias matches.
     c) fallback to the configured default material.
   Components with material == "sin_material" are treated as blank and go
   straight to the fallback.

2. group(): group a list of Layer-1 components by material_id.  Each group
   carries the resolved MaterialSpec and the total gross area in m².
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class MaterialSpec:
    id: str
    nombre: str
    espesor_mm: float
    precio_usd_m2: float
    hoja_largo_mm: float
    hoja_ancho_mm: float
    aliases: list[str] = field(default_factory=list)


@dataclass
class MaterialGroup:
    material_id: str
    spec: MaterialSpec
    piezas: list[dict] = field(default_factory=list)
    area_bruta_m2: float = 0.0


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class MaterialGrouper:
    """Resolve free-text material names to catalog entries and group pieces."""

    def __init__(self, config: dict) -> None:
        self._config = config
        self._catalog: dict[str, MaterialSpec] = self._build_catalog()
        self._default_id: str = config.get("material_default", "mdf_18")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve_material(self, material_name: str, espesor_mm: float) -> MaterialSpec:
        """
        Resolve a free-text material name + espesor to a catalog MaterialSpec.

        Falls back to the default material if no match is found.
        """
        name_norm = (material_name or "").strip().lower()

        # Treat blank / sin_material as no name → go to espesor/default path
        if not name_norm or name_norm == "sin_material":
            return self._match_by_espesor(espesor_mm) or self._default()

        # a) Alias match
        candidates = [
            spec for spec in self._catalog.values()
            if any(alias.lower() == name_norm for alias in spec.aliases)
        ]

        if len(candidates) == 1:
            return candidates[0]

        if len(candidates) > 1:
            # Disambiguate by espesor proximity
            return min(candidates, key=lambda s: abs(s.espesor_mm - espesor_mm))

        # b) No alias match — try espesor alone
        spec = self._match_by_espesor(espesor_mm)
        if spec:
            logger.debug(
                "Material '%s' not found in catalog; matched by espesor %.1f → %s",
                material_name, espesor_mm, spec.id,
            )
            return spec

        # c) Default fallback
        logger.debug(
            "Material '%s' espesor=%.1f not matched; using default '%s'",
            material_name, espesor_mm, self._default_id,
        )
        return self._default()

    def group(self, componentes: list[dict]) -> list[MaterialGroup]:
        """
        Group Layer-1 components by resolved material_id.

        Area is computed as: largo_mm × ancho_mm × cantidad (mm² → m²).
        Returns a list of MaterialGroup sorted by material_id for determinism.
        """
        groups: dict[str, MaterialGroup] = {}

        for comp in componentes:
            dims = comp.get("dimensiones", {})
            largo = float(dims.get("largo", 0))
            ancho = float(dims.get("ancho", 0))
            espesor = float(dims.get("espesor", 0))
            cantidad = int(comp.get("cantidad", 1))

            spec = self.resolve_material(comp.get("material", ""), espesor)

            if spec.id not in groups:
                groups[spec.id] = MaterialGroup(
                    material_id=spec.id,
                    spec=spec,
                )

            groups[spec.id].piezas.append(comp)
            area_m2 = (largo * ancho * cantidad) / 1_000_000
            groups[spec.id].area_bruta_m2 += area_m2

        return sorted(groups.values(), key=lambda g: g.material_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_catalog(self) -> dict[str, MaterialSpec]:
        catalog: dict[str, MaterialSpec] = {}
        for mat_id, data in self._config.get("materiales", {}).items():
            catalog[mat_id] = MaterialSpec(
                id=mat_id,
                nombre=data.get("nombre", mat_id),
                espesor_mm=float(data.get("espesor_mm", 18)),
                precio_usd_m2=float(data.get("precio_usd_m2", 0)),
                hoja_largo_mm=float(data.get("hoja_largo_mm", 2750)),
                hoja_ancho_mm=float(data.get("hoja_ancho_mm", 1830)),
                aliases=[str(a).lower() for a in data.get("aliases", [])],
            )
        return catalog

    def _match_by_espesor(self, espesor_mm: float) -> MaterialSpec | None:
        if espesor_mm <= 0:
            return None
        close = [s for s in self._catalog.values() if abs(s.espesor_mm - espesor_mm) <= 2]
        if not close:
            return None
        return min(close, key=lambda s: abs(s.espesor_mm - espesor_mm))

    def _default(self) -> MaterialSpec:
        return self._catalog[self._default_id]
