"""
SKP Parser Agent — Capa 1.

Loads a SketchUp .skp file via the pyslapi SDK (Python package: sketchup),
extracts the full component/group hierarchy, converts all dimensions from
inches to millimetres, runs the cascade classifier on every component, and
returns the Layer-1 canonical JSON defined in docs/schemas.md.

pyslapi is an optional native dependency (requires the SketchUp C SDK).
If it is not installed the agent raises ImportError with installation
instructions. For testing, override ``_load_raw_components`` with a stub.

Coordinate conventions
-----------------------
SketchUp stores geometry internally in **inches**.
Conversion: 1 inch = 25.4 mm  (INCH_TO_MM constant).

The bounding box of an instance gives its extents in the local coordinate
system of its parent definition.  We sort the three axis-aligned extents so
that: espesor = min, ancho = mid, largo = max — matching the canonical schema.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from typing import TYPE_CHECKING

from src.agents.classifier import CascadeClassifier, ClassifiedComponent, RawComponent
from src.models.project import TipoInferido

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

INCH_TO_MM: float = 25.4


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _inches_to_mm(value: float) -> float:
    return value * INCH_TO_MM


def _extract_dims_mm(bounding_box: object) -> tuple[float, float, float]:
    """
    Extract (largo_mm, ancho_mm, espesor_mm) from a pyslapi BoundingBox.

    The box exposes ``min_point`` and ``max_point`` with ``.x / .y / .z``
    attributes in inches.  We convert, then sort descending so:
      index 0 = largo  (largest)
      index 1 = ancho  (middle)
      index 2 = espesor (smallest)
    """
    min_pt = bounding_box.min_point
    max_pt = bounding_box.max_point
    dims_mm = sorted(
        [
            abs(max_pt.x - min_pt.x) * INCH_TO_MM,
            abs(max_pt.y - min_pt.y) * INCH_TO_MM,
            abs(max_pt.z - min_pt.z) * INCH_TO_MM,
        ],
        reverse=True,
    )
    return dims_mm[0], dims_mm[1], dims_mm[2]  # largo, ancho, espesor


def _get_material_name(entity: object) -> str:
    """Return the material name from an instance or group, or 'sin_material'."""
    try:
        mat = entity.material  # type: ignore[attr-defined]
        if mat is not None:
            return mat.name  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass
    return "sin_material"


def _to_canonical_json(
    proyecto_id: str,
    components: list[ClassifiedComponent],
    advertencias: list[str],
    requiere_revision: list[str],
) -> dict:
    return {
        "proyecto_id": proyecto_id,
        "origen": "skp",
        "componentes": [
            {
                "id": c.id,
                "name": c.name,
                "parent": c.parent_id,
                "tipo_inferido": c.tipo_inferido.value,
                "subtype": c.subtype,
                "dimensiones": {
                    "largo": round(c.largo_mm, 1),
                    "ancho": round(c.ancho_mm, 1),
                    "espesor": round(c.espesor_mm, 1),
                },
                "material": c.material,
                "cantidad": c.cantidad,
                "confidence": round(c.confidence, 3),
                "classification_method": c.method.value,
            }
            for c in components
        ],
        "advertencias": advertencias,
        "requiere_revision": requiere_revision,
    }


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class SKPParserAgent:
    """
    Parse a SketchUp file and return the Layer-1 canonical JSON.

    Usage::

        agent = SKPParserAgent()
        result = await agent.parse("path/to/file.skp", proyecto_id="proj-001")

    Testing::

        agent = SKPParserAgent()
        agent._load_raw_components = lambda path: [RawComponent(...), ...]
        result = await agent.parse("dummy.skp", proyecto_id="test")
    """

    # Components with confidence below this threshold are added to
    # ``requiere_revision`` in the output JSON.
    REVISION_THRESHOLD: float = 0.60

    def __init__(self, classifier: CascadeClassifier | None = None) -> None:
        self.classifier = classifier or CascadeClassifier()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def parse(self, filepath: str, proyecto_id: str = "") -> dict:
        """
        Full pipeline: load → classify → canonical JSON.

        Parameters
        ----------
        filepath:    path to the .skp file
        proyecto_id: identifier forwarded into the output JSON
        """
        raw_components = self._load_raw_components(filepath)

        classified: list[ClassifiedComponent] = []
        advertencias: list[str] = []
        requiere_revision: list[str] = []

        for raw in raw_components:
            try:
                comp = await self.classifier.classify(raw)
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to classify '%s': %s", raw.name, exc)
                advertencias.append(f"Classification error for '{raw.name}': {exc}")
                comp = ClassifiedComponent.from_raw(
                    raw, TipoInferido.otro, 0.0,
                    __import__("src.models.project", fromlist=["ClassificationMethod"])
                    .ClassificationMethod.dimension_rule,
                )

            classified.append(comp)
            if comp.confidence < self.REVISION_THRESHOLD:
                requiere_revision.append(comp.id)

        return _to_canonical_json(proyecto_id, classified, advertencias, requiere_revision)

    # ------------------------------------------------------------------
    # pyslapi interface (override in tests)
    # ------------------------------------------------------------------

    def _load_raw_components(self, filepath: str) -> list[RawComponent]:
        """
        Load raw component data from a .skp file using the pyslapi SDK.

        This method is the only point of contact with the native pyslapi
        library; override it in tests to inject mock data without needing
        the SDK installed.

        Raises
        ------
        ImportError
            When pyslapi (Python package: ``sketchup``) is not installed.
        FileNotFoundError
            When ``filepath`` does not exist.
        """
        try:
            import sketchup  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "pyslapi is required to parse .skp files. "
                "Build it from source with the SketchUp C SDK: "
                "https://github.com/martijnberger/pyslapi"
            ) from exc

        logger.info("Loading SKP model: %s", filepath)
        model = sketchup.Model.from_file(filepath)
        try:
            components = list(self._walk_entities(model.entities, parent_id=None))
        finally:
            model.close()

        logger.info("Extracted %d raw components from %s", len(components), filepath)
        return components

    # ------------------------------------------------------------------
    # Hierarchy traversal
    # ------------------------------------------------------------------

    def _walk_entities(
        self,
        entities: object,
        parent_id: str | None,
    ) -> Iterator[RawComponent]:
        """
        Recursively walk pyslapi Entities, yielding one RawComponent per
        ComponentInstance and per Group.
        """
        # --- ComponentInstances ---
        for instance in entities.component_instances:  # type: ignore[attr-defined]
            comp_id = str(uuid.uuid4())
            defn = instance.definition
            name: str = defn.name or "component"

            try:
                largo, ancho, espesor = _extract_dims_mm(instance.bounding_box)
            except Exception:  # noqa: BLE001
                logger.warning("Could not extract dimensions for '%s'", name)
                largo, ancho, espesor = 0.0, 0.0, 0.0

            material = _get_material_name(instance)

            yield RawComponent(
                id=comp_id,
                name=name,
                parent_id=parent_id,
                largo_mm=largo,
                ancho_mm=ancho,
                espesor_mm=espesor,
                material=material,
            )

            # Recurse into the definition's child entities
            try:
                yield from self._walk_entities(defn.entities, parent_id=comp_id)
            except Exception:  # noqa: BLE001
                pass  # leaf node — no child entities

        # --- Groups ---
        for group in entities.groups:  # type: ignore[attr-defined]
            grp_id = str(uuid.uuid4())
            name = getattr(group, "name", None) or "group"

            try:
                largo, ancho, espesor = _extract_dims_mm(group.bounding_box)
            except Exception:  # noqa: BLE001
                logger.warning("Could not extract dimensions for group '%s'", name)
                largo, ancho, espesor = 0.0, 0.0, 0.0

            material = _get_material_name(group)

            yield RawComponent(
                id=grp_id,
                name=name,
                parent_id=parent_id,
                largo_mm=largo,
                ancho_mm=ancho,
                espesor_mm=espesor,
                material=material,
            )

            try:
                yield from self._walk_entities(group.entities, parent_id=grp_id)
            except Exception:  # noqa: BLE001
                pass
