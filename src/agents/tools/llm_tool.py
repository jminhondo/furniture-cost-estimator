"""
LLM-based component classifier (last resort in cascade).

Calls Claude claude-sonnet-4-6 with a structured prompt describing the component.
Returns (TipoInferido, confidence) or None if the model cannot classify it.
"""

import json
import logging

from anthropic import AsyncAnthropic

from src.models.project import TipoInferido

logger = logging.getLogger(__name__)

_VALID_TYPES = [t.value for t in TipoInferido]

_SYSTEM_PROMPT = """\
You are an expert in custom furniture manufacturing (carpintería a medida).
You will receive a JSON object describing a component extracted from a SketchUp
model and must classify it into exactly one of the following types:

{types}

Respond ONLY with a JSON object in this exact format:
{{"tipo": "<one of the types above>", "confidence": <float 0.0-1.0>, "reason": "<one sentence>"}}

Rules:
- If the component is a thin panel (espesor ≤ 6 mm), classify as "fondo".
- Use "otro" only when none of the other types fit.
- confidence must reflect your certainty (≥ 0.7 means confident).
""".format(types=", ".join(_VALID_TYPES))

_USER_TEMPLATE = """\
Classify this furniture component:
{{
  "name": "{name}",
  "largo_mm": {largo_mm},
  "ancho_mm": {ancho_mm},
  "espesor_mm": {espesor_mm},
  "material": "{material}"
}}
"""


class LLMClassifierTool:
    """Classify a component using Claude when rule-based tools fail."""

    MODEL = "claude-sonnet-4-6"
    MAX_TOKENS = 256

    def __init__(self, client: AsyncAnthropic | None = None) -> None:
        self._client = client or AsyncAnthropic()

    async def classify(
        self,
        name: str,
        largo_mm: float,
        ancho_mm: float,
        espesor_mm: float,
        material: str = "desconocido",
    ) -> tuple[TipoInferido, float] | None:
        """
        Send component details to Claude and parse the structured response.
        Returns None on any error so the cascade can fall back gracefully.
        """
        user_msg = _USER_TEMPLATE.format(
            name=name,
            largo_mm=round(largo_mm, 1),
            ancho_mm=round(ancho_mm, 1),
            espesor_mm=round(espesor_mm, 1),
            material=material,
        )

        try:
            response = await self._client.messages.create(
                model=self.MODEL,
                max_tokens=self.MAX_TOKENS,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
            )
            raw = response.content[0].text.strip()
            data = json.loads(raw)

            tipo_str = data.get("tipo", "otro")
            if tipo_str not in _VALID_TYPES:
                logger.warning("LLM returned unknown tipo '%s', defaulting to 'otro'", tipo_str)
                tipo_str = "otro"

            confidence = float(data.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))

            return TipoInferido(tipo_str), confidence

        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM classification failed for '%s': %s", name, exc)
            return None
