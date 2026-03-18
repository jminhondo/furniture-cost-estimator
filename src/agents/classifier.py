"""
Cascade classifier for furniture components.

Pipeline: NameClassifierTool → DimensionClassifierTool → LLMClassifierTool

Each step is attempted in order; the first successful classification wins.
If all steps fail, the component is labelled TipoInferido.otro with confidence 0.0.
"""

from dataclasses import dataclass, field

from src.agents.tools.dimension_tool import DimensionClassifierTool
from src.agents.tools.llm_tool import LLMClassifierTool
from src.agents.tools.name_tool import NameClassifierTool
from src.models.project import ClassificationMethod, TipoInferido


# ---------------------------------------------------------------------------
# Data transfer objects
# ---------------------------------------------------------------------------


@dataclass
class RawComponent:
    """Intermediate representation of a parsed SKP component (pre-classification)."""

    id: str
    name: str
    parent_id: str | None
    largo_mm: float   # largest dimension  (mm)
    ancho_mm: float   # middle dimension   (mm)
    espesor_mm: float  # smallest dimension (mm)
    material: str
    cantidad: int = 1


@dataclass
class ClassifiedComponent:
    """RawComponent enriched with classification results."""

    id: str
    name: str
    parent_id: str | None
    largo_mm: float
    ancho_mm: float
    espesor_mm: float
    material: str
    cantidad: int
    tipo_inferido: TipoInferido
    confidence: float
    method: ClassificationMethod
    subtype: str | None = None

    @classmethod
    def from_raw(
        cls,
        raw: RawComponent,
        tipo_inferido: TipoInferido,
        confidence: float,
        method: ClassificationMethod,
        subtype: str | None = None,
    ) -> "ClassifiedComponent":
        return cls(
            id=raw.id,
            name=raw.name,
            parent_id=raw.parent_id,
            largo_mm=raw.largo_mm,
            ancho_mm=raw.ancho_mm,
            espesor_mm=raw.espesor_mm,
            material=raw.material,
            cantidad=raw.cantidad,
            tipo_inferido=tipo_inferido,
            confidence=confidence,
            method=method,
            subtype=subtype,
        )


# ---------------------------------------------------------------------------
# Cascade classifier
# ---------------------------------------------------------------------------


class CascadeClassifier:
    """
    Three-step cascade:
      1. NameClassifierTool    (keyword regex on component name)
      2. DimensionClassifierTool (espesor / ratio rules)
      3. LLMClassifierTool     (Claude — only if llm_tool is provided)
    """

    def __init__(
        self,
        name_tool: NameClassifierTool | None = None,
        dimension_tool: DimensionClassifierTool | None = None,
        llm_tool: LLMClassifierTool | None = None,
    ) -> None:
        self.name_tool = name_tool or NameClassifierTool()
        self.dimension_tool = dimension_tool or DimensionClassifierTool()
        self.llm_tool = llm_tool  # optional; skipped when None

    async def classify(self, raw: RawComponent) -> ClassifiedComponent:
        # ── Step 1: name patterns ─────────────────────────────────────────
        result = self.name_tool.classify(raw.name)
        if result is not None:
            tipo, confidence = result
            return ClassifiedComponent.from_raw(
                raw, tipo, confidence, ClassificationMethod.name_match
            )

        # ── Step 2: dimension rules ───────────────────────────────────────
        result = self.dimension_tool.classify(raw.largo_mm, raw.ancho_mm, raw.espesor_mm)
        if result is not None:
            tipo, confidence = result
            return ClassifiedComponent.from_raw(
                raw, tipo, confidence, ClassificationMethod.dimension_rule
            )

        # ── Step 3: LLM (only when a tool is configured) ─────────────────
        if self.llm_tool is not None:
            result = await self.llm_tool.classify(
                name=raw.name,
                largo_mm=raw.largo_mm,
                ancho_mm=raw.ancho_mm,
                espesor_mm=raw.espesor_mm,
                material=raw.material,
            )
            if result is not None:
                tipo, confidence = result
                return ClassifiedComponent.from_raw(
                    raw, tipo, confidence, ClassificationMethod.llm
                )

        # ── Fallback ──────────────────────────────────────────────────────
        return ClassifiedComponent.from_raw(
            raw, TipoInferido.otro, 0.0, ClassificationMethod.dimension_rule
        )
