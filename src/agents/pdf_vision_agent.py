"""
PDF Vision Agent — Capa 1, origen ``pdf``.

Converts a PDF of furniture technical drawings into the same Layer-1 canonical
JSON that the SKP Parser produces (docs/schemas.md), so Layer 2 (BOM Builder)
can consume both origins without distinction.

Pipeline
--------
1. pdf_to_images()           — convert every page to a PIL Image at 300 dpi
                               (uses pdf2image / poppler; overrideable for tests)
2. classify_page()           — Claude Vision: planta | alzado | detalle_pieza |
                               tabla_materiales | caratula | otro
3. extract_furniture_parts() — Claude Vision with carpentry expert system prompt;
                               returns structured JSON per page
4. consolidate_parts()       — deduplicate parts that appear in multiple views
                               (same tipo + dimensions within ±10 mm bucket)
5. Flag requiere_revision    — parts with confidence < REVISION_THRESHOLD
6. Build canonical JSON      — matches docs/schemas.md exactly

Design notes
------------
``_call_claude_vision`` is the single point of contact with the Anthropic API.
Override it (or ``pdf_to_images``) via monkeypatch in tests to avoid real
network calls and the poppler dependency.
"""

from __future__ import annotations

import base64
import enum
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from io import BytesIO
from typing import TYPE_CHECKING

from anthropic import AsyncAnthropic

from src.models.project import ClassificationMethod, TipoInferido

if TYPE_CHECKING:
    from PIL.Image import Image

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Page types
# ---------------------------------------------------------------------------


class PageType(str, enum.Enum):
    planta = "planta"
    alzado = "alzado"
    detalle_pieza = "detalle_pieza"
    tabla_materiales = "tabla_materiales"
    caratula = "caratula"
    otro = "otro"


# ---------------------------------------------------------------------------
# Intermediate data structure
# ---------------------------------------------------------------------------


@dataclass
class ExtractedPart:
    """A furniture piece extracted from a single PDF page."""

    id: str
    name: str
    tipo_inferido: TipoInferido
    largo_mm: float
    ancho_mm: float
    espesor_mm: float
    material: str
    cantidad: int
    confidence: float
    page_number: int
    source_view: PageType
    parent_id: str | None = None
    subtype: str | None = None


# ---------------------------------------------------------------------------
# Prompt constants
# ---------------------------------------------------------------------------

_VALID_PAGE_TYPES = [t.value for t in PageType]
_VALID_TIPOS = [t.value for t in TipoInferido]

_CLASSIFY_SYSTEM = (
    "You are an expert at reading technical furniture drawings and architectural plans. "
    "You will receive an image of a single page from a PDF and must classify it."
)

_CLASSIFY_USER = """\
Classify this page from a furniture technical drawing PDF.

Valid page types:
- planta: floor plan / top view
- alzado: elevation / front view / side view
- detalle_pieza: individual piece detail with dimensions
- tabla_materiales: materials list or cut list table
- caratula: title page / cover sheet
- otro: anything else (photo, text only, etc.)

Respond ONLY with valid JSON (no markdown fences):
{{"tipo": "<one of the types above>", "confidence": <float 0.0-1.0>}}
"""

_EXTRACT_SYSTEM = (
    "Sos un carpintero experto leyendo planos técnicos de muebles a medida. "
    "Tu tarea es identificar y extraer cada pieza de mueble visible en el plano, "
    "con sus dimensiones exactas en milímetros, material y cantidad."
)

_EXTRACT_USER_TEMPLATE = """\
Analizá este plano tipo "{page_type}" y extraé TODAS las piezas de mueble visibles.

Para cada pieza completá estos campos:
- tipo: uno de {tipos}
- nombre: nombre descriptivo de la pieza
- largo_mm: dimensión mayor en milímetros (float)
- ancho_mm: dimensión media en milímetros (float)
- espesor_mm: dimensión menor / espesor en milímetros (float)
- material: material (MDF, melamina, madera maciza, HDF, etc.) o "desconocido"
- cantidad: número entero de piezas iguales (default 1)
- confidence: tu confianza en la extracción, float 0.0-1.0

Si no ves dimensiones claras para una pieza, estimá y bajá la confianza.
Si la página no tiene piezas de mueble, devolvé una lista vacía.

Respondé SOLO con JSON válido (sin markdown):
{{"piezas": [
  {{"tipo": "...", "nombre": "...", "largo_mm": 0, "ancho_mm": 0, "espesor_mm": 0,
    "material": "...", "cantidad": 1, "confidence": 0.0}}
]}}
"""


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class PDFVisionAgent:
    """
    Parse a PDF of furniture technical drawings into canonical Layer-1 JSON.

    Usage::

        agent = PDFVisionAgent()
        result = await agent.parse("planos_cocina.pdf", proyecto_id="proj-002")

    Testing::

        agent = PDFVisionAgent()
        agent.pdf_to_images = lambda path: [PIL_image]
        agent._call_claude_vision = AsyncMock(return_value='{"tipo":"alzado",...}')
        result = await agent.parse("dummy.pdf", proyecto_id="test")
    """

    MODEL = "claude-3-5-haiku-20241022"
    MAX_TOKENS = 1024
    REVISION_THRESHOLD = 0.60

    # Page types that may contain extractable furniture parts
    EXTRACTABLE_PAGE_TYPES: frozenset[PageType] = frozenset(
        {PageType.planta, PageType.alzado, PageType.detalle_pieza}
    )

    def __init__(self, client: AsyncAnthropic | None = None) -> None:
        self.client = client or AsyncAnthropic()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def parse(self, filepath: str, proyecto_id: str = "") -> dict:
        """
        Full pipeline: PDF → images → classify → extract → consolidate → JSON.
        """
        images = self.pdf_to_images(filepath)
        logger.info("Loaded %d pages from %s", len(images), filepath)

        all_parts: list[ExtractedPart] = []
        advertencias: list[str] = []

        for page_num, image in enumerate(images, start=1):
            try:
                page_type = await self.classify_page(image, page_num)
                logger.debug("Page %d classified as: %s", page_num, page_type.value)
            except Exception as exc:  # noqa: BLE001
                msg = f"Page {page_num}: classification failed — {exc}"
                logger.warning(msg)
                advertencias.append(msg)
                page_type = PageType.otro

            if page_type not in self.EXTRACTABLE_PAGE_TYPES:
                logger.debug("Page %d skipped (%s)", page_num, page_type.value)
                continue

            try:
                parts = await self.extract_furniture_parts(image, page_type, page_num)
                logger.debug("Page %d: extracted %d parts", page_num, len(parts))
                all_parts.extend(parts)
            except Exception as exc:  # noqa: BLE001
                msg = f"Page {page_num}: extraction failed — {exc}"
                logger.warning(msg)
                advertencias.append(msg)

        consolidated = self.consolidate_parts(all_parts)
        requiere_revision = [p.id for p in consolidated if p.confidence < self.REVISION_THRESHOLD]

        return _to_canonical_json(proyecto_id, consolidated, advertencias, requiere_revision)

    # ------------------------------------------------------------------
    # Step 1 — PDF → images
    # ------------------------------------------------------------------

    def pdf_to_images(self, filepath: str) -> list["Image"]:
        """
        Convert every PDF page to a 300-dpi PIL Image.

        Requires **poppler** to be installed (``pdftoppm`` on PATH).
        Override this method in tests to inject PIL images directly.
        """
        from pdf2image import convert_from_path  # noqa: PLC0415

        return convert_from_path(filepath, dpi=300)

    # ------------------------------------------------------------------
    # Step 2 — Page classification
    # ------------------------------------------------------------------

    async def classify_page(self, image: "Image", page_num: int) -> PageType:
        """
        Ask Claude Vision to classify the page type.
        Returns PageType; falls back to PageType.otro on parse error.
        """
        raw = await self._call_claude_vision(image, _CLASSIFY_SYSTEM, _CLASSIFY_USER)
        try:
            data = _parse_json(raw)
            tipo_str = data.get("tipo", "otro")
            if tipo_str not in _VALID_PAGE_TYPES:
                logger.warning("Page %d: unknown page type '%s'", page_num, tipo_str)
                tipo_str = "otro"
            return PageType(tipo_str)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Page %d: could not parse classification response: %s", page_num, exc)
            return PageType.otro

    # ------------------------------------------------------------------
    # Step 3 — Part extraction
    # ------------------------------------------------------------------

    async def extract_furniture_parts(
        self, image: "Image", page_type: PageType, page_num: int
    ) -> list[ExtractedPart]:
        """
        Ask Claude Vision to extract all furniture parts from a page.

        System prompt: expert carpenter reading technical drawings.
        Returns a (possibly empty) list of ExtractedPart objects.
        """
        user_msg = _EXTRACT_USER_TEMPLATE.format(
            page_type=page_type.value,
            tipos=", ".join(_VALID_TIPOS),
        )
        raw = await self._call_claude_vision(image, _EXTRACT_SYSTEM, user_msg)

        try:
            data = _parse_json(raw)
            piezas = data.get("piezas", [])
        except Exception as exc:  # noqa: BLE001
            logger.warning("Page %d: could not parse extraction response: %s", page_num, exc)
            return []

        parts: list[ExtractedPart] = []
        for p in piezas:
            tipo_str = p.get("tipo", "otro")
            if tipo_str not in _VALID_TIPOS:
                tipo_str = "otro"

            try:
                largo = float(p.get("largo_mm", 0) or 0)
                ancho = float(p.get("ancho_mm", 0) or 0)
                espesor = float(p.get("espesor_mm", 0) or 0)
            except (TypeError, ValueError):
                largo = ancho = espesor = 0.0

            # Enforce dim ordering: largo ≥ ancho ≥ espesor
            dims = sorted([largo, ancho, espesor], reverse=True)

            confidence = float(p.get("confidence", 0.5) or 0.5)
            confidence = max(0.0, min(1.0, confidence))

            parts.append(
                ExtractedPart(
                    id=str(uuid.uuid4()),
                    name=str(p.get("nombre", tipo_str)),
                    tipo_inferido=TipoInferido(tipo_str),
                    largo_mm=dims[0],
                    ancho_mm=dims[1],
                    espesor_mm=dims[2],
                    material=str(p.get("material", "desconocido")),
                    cantidad=int(p.get("cantidad", 1) or 1),
                    confidence=confidence,
                    page_number=page_num,
                    source_view=page_type,
                )
            )
        return parts

    # ------------------------------------------------------------------
    # Step 4 — Consolidation / deduplication
    # ------------------------------------------------------------------

    def consolidate_parts(self, parts: list[ExtractedPart]) -> list[ExtractedPart]:
        """
        Deduplicate parts that appear in multiple views of the same drawing.

        Two parts are considered the same when they share:
          (tipo_inferido, round(largo,10mm), round(ancho,10mm), round(espesor,10mm))

        When duplicates exist, the entry with the highest confidence is kept.
        """
        best: dict[tuple, ExtractedPart] = {}
        for part in parts:
            key = _dedup_key(part)
            if key not in best or part.confidence > best[key].confidence:
                best[key] = part
        return list(best.values())

    # ------------------------------------------------------------------
    # Claude Vision — single integration point
    # ------------------------------------------------------------------

    async def _call_claude_vision(
        self,
        image: "Image",
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """
        Encode the image as PNG base64 and send it to Claude Vision.
        Returns the raw text response from the model.

        Override this method in tests to avoid real API calls.
        """
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        b64_data = base64.standard_b64encode(buffer.getvalue()).decode()

        response = await self.client.messages.create(
            model=self.MODEL,
            max_tokens=self.MAX_TOKENS,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": b64_data,
                            },
                        },
                        {"type": "text", "text": user_prompt},
                    ],
                }
            ],
        )
        return response.content[0].text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_json(text: str) -> dict:
    """
    Parse JSON from Claude's response.
    Strips markdown code fences (```json ... ```) if present.
    """
    text = text.strip()
    # Remove markdown fences: ```json ... ``` or ``` ... ```
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text.strip())


def _round_dim(v: float) -> int:
    """Round a dimension to the nearest 10 mm bucket for deduplication."""
    if v <= 0:
        return 0
    return round(v / 10) * 10


def _dedup_key(part: ExtractedPart) -> tuple:
    return (
        part.tipo_inferido,
        _round_dim(part.largo_mm),
        _round_dim(part.ancho_mm),
        _round_dim(part.espesor_mm),
    )


def _to_canonical_json(
    proyecto_id: str,
    parts: list[ExtractedPart],
    advertencias: list[str],
    requiere_revision: list[str],
) -> dict:
    return {
        "proyecto_id": proyecto_id,
        "origen": "pdf",
        "componentes": [
            {
                "id": p.id,
                "name": p.name,
                "parent": p.parent_id,
                "tipo_inferido": p.tipo_inferido.value,
                "subtype": p.subtype,
                "dimensiones": {
                    "largo": round(p.largo_mm, 1),
                    "ancho": round(p.ancho_mm, 1),
                    "espesor": round(p.espesor_mm, 1),
                },
                "material": p.material,
                "cantidad": p.cantidad,
                "confidence": round(p.confidence, 3),
                "classification_method": ClassificationMethod.llm.value,
            }
            for p in parts
        ],
        "advertencias": advertencias,
        "requiere_revision": requiere_revision,
    }
