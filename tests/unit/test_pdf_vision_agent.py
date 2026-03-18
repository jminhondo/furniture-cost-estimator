"""
Unit tests for PDFVisionAgent.

All Claude API calls are intercepted by patching ``_call_claude_vision`` with
an AsyncMock that returns pre-built JSON strings.  ``pdf_to_images`` is also
replaced so tests work without poppler.

Test matrix
-----------
test_classify_page_detects_alzado        — Step 2: page classification
test_extract_parts_returns_dimensions    — Step 3: part extraction + dim ordering
test_low_confidence_flagged_for_review   — Step 5: revision flagging
test_output_matches_canonical_schema     — full pipeline → schema validation
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image

from src.agents.pdf_vision_agent import (
    ExtractedPart,
    PDFVisionAgent,
    PageType,
    _dedup_key,
    _round_dim,
)
from src.models.project import ClassificationMethod, TipoInferido

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _blank_image(w: int = 200, h: int = 200) -> Image.Image:
    return Image.new("RGB", (w, h), color=(255, 255, 255))


def _agent_with_mocks(
    monkeypatch,
    classify_response: str,
    extract_response: str,
    images: list[Image.Image] | None = None,
) -> PDFVisionAgent:
    """
    Build a PDFVisionAgent whose Vision calls are mocked:
      - pdf_to_images   → returns ``images`` (or a single blank image)
      - _call_claude_vision → alternates between classify_response and
                              extract_response on successive calls
    """
    _images = images or [_blank_image()]
    agent = PDFVisionAgent()

    # Replace pdf_to_images synchronously
    monkeypatch.setattr(agent, "pdf_to_images", lambda _path: _images)

    # _call_claude_vision is async; we set up side_effect to alternate responses
    call_responses = [classify_response, extract_response] * len(_images)
    mock_vision = AsyncMock(side_effect=call_responses)
    monkeypatch.setattr(agent, "_call_claude_vision", mock_vision)

    return agent


# ---------------------------------------------------------------------------
# test_classify_page_detects_alzado
# ---------------------------------------------------------------------------


async def test_classify_page_detects_alzado(monkeypatch):
    """
    classify_page() must correctly parse a Claude response and return
    the matching PageType enum value.
    """
    agent = PDFVisionAgent()
    image = _blank_image()

    response_json = json.dumps({"tipo": "alzado", "confidence": 0.95})
    mock_vision = AsyncMock(return_value=response_json)
    monkeypatch.setattr(agent, "_call_claude_vision", mock_vision)

    result = await agent.classify_page(image, page_num=1)

    assert result is PageType.alzado
    mock_vision.assert_called_once()

    # Also verify other page types are correctly mapped
    for tipo in PageType:
        mock_vision.return_value = json.dumps({"tipo": tipo.value, "confidence": 0.80})
        r = await agent.classify_page(image, page_num=1)
        assert r is tipo

    # Unknown tipo → falls back to PageType.otro
    mock_vision.return_value = json.dumps({"tipo": "plano_3d", "confidence": 0.5})
    r = await agent.classify_page(image, page_num=1)
    assert r is PageType.otro


# ---------------------------------------------------------------------------
# test_extract_parts_returns_dimensions
# ---------------------------------------------------------------------------


async def test_extract_parts_returns_dimensions(monkeypatch):
    """
    extract_furniture_parts() must return parts with correct, sorted dimensions.

    Dimensions from Claude may arrive in any order; the agent must sort them
    so that: largo ≥ ancho ≥ espesor (canonical schema requirement).
    """
    agent = PDFVisionAgent()
    image = _blank_image()

    # Claude returns unsorted dims (espesor=18 largest in position 0 — intentionally wrong)
    extract_payload = {
        "piezas": [
            {
                "tipo": "puerta",
                "nombre": "Puerta Cocina",
                "largo_mm": 700,
                "ancho_mm": 600,
                "espesor_mm": 18,
                "material": "MDF",
                "cantidad": 1,
                "confidence": 0.88,
            },
            {
                # Dimensions arriving out of order — agent must sort
                "tipo": "lateral",
                "nombre": "Lateral Izquierdo",
                "largo_mm": 18,    # this is actually espesor
                "ancho_mm": 2400,  # this is actually largo
                "espesor_mm": 600, # this is actually ancho
                "material": "MDF",
                "cantidad": 2,
                "confidence": 0.75,
            },
        ]
    }
    mock_vision = AsyncMock(return_value=json.dumps(extract_payload))
    monkeypatch.setattr(agent, "_call_claude_vision", mock_vision)

    parts = await agent.extract_furniture_parts(image, PageType.alzado, page_num=1)

    assert len(parts) == 2

    puerta = next(p for p in parts if p.tipo_inferido == TipoInferido.puerta)
    assert puerta.largo_mm == pytest.approx(700.0)
    assert puerta.ancho_mm == pytest.approx(600.0)
    assert puerta.espesor_mm == pytest.approx(18.0)
    assert puerta.confidence == pytest.approx(0.88)
    assert puerta.material == "MDF"
    assert puerta.cantidad == 1

    lateral = next(p for p in parts if p.tipo_inferido == TipoInferido.lateral)
    # After sorting: 2400 → largo, 600 → ancho, 18 → espesor
    assert lateral.largo_mm == pytest.approx(2400.0)
    assert lateral.ancho_mm == pytest.approx(600.0)
    assert lateral.espesor_mm == pytest.approx(18.0)

    # Verify all IDs are unique
    ids = [p.id for p in parts]
    assert len(set(ids)) == len(ids)


# ---------------------------------------------------------------------------
# test_low_confidence_flagged_for_review
# ---------------------------------------------------------------------------


async def test_low_confidence_flagged_for_review(monkeypatch):
    """
    Parts with confidence < REVISION_THRESHOLD (0.60) must appear in the
    ``requiere_revision`` list of the output JSON.  High-confidence parts
    must NOT appear there.
    """
    classify_json = json.dumps({"tipo": "detalle_pieza", "confidence": 0.90})
    extract_json = json.dumps(
        {
            "piezas": [
                {
                    "tipo": "puerta",
                    "nombre": "Pieza alta confianza",
                    "largo_mm": 700,
                    "ancho_mm": 600,
                    "espesor_mm": 18,
                    "material": "MDF",
                    "cantidad": 1,
                    "confidence": 0.85,  # above threshold
                },
                {
                    "tipo": "otro",
                    "nombre": "Pieza dudosa",
                    "largo_mm": 300,
                    "ancho_mm": 200,
                    "espesor_mm": 15,
                    "material": "desconocido",
                    "cantidad": 1,
                    "confidence": 0.35,  # below threshold
                },
                {
                    "tipo": "lateral",
                    "nombre": "Justo en el borde",
                    "largo_mm": 2000,
                    "ancho_mm": 580,
                    "espesor_mm": 18,
                    "material": "MDF",
                    "cantidad": 1,
                    "confidence": 0.59,  # just below threshold
                },
            ]
        }
    )

    agent = _agent_with_mocks(monkeypatch, classify_json, extract_json)
    result = await agent.parse("dummy.pdf", proyecto_id="test-low-conf")

    assert result["proyecto_id"] == "test-low-conf"
    assert result["origen"] == "pdf"

    comps = result["componentes"]
    assert len(comps) == 3

    high_conf = next(c for c in comps if "alta confianza" in c["name"])
    dudosa = next(c for c in comps if "dudosa" in c["name"])
    borde = next(c for c in comps if "borde" in c["name"])

    revision_ids = set(result["requiere_revision"])

    assert high_conf["id"] not in revision_ids, "High-confidence part should NOT be flagged"
    assert dudosa["id"] in revision_ids, "Low-confidence part MUST be flagged"
    assert borde["id"] in revision_ids, "Just-below-threshold part MUST be flagged"


# ---------------------------------------------------------------------------
# test_output_matches_canonical_schema
# ---------------------------------------------------------------------------


async def test_output_matches_canonical_schema(monkeypatch):
    """
    Full parse() pipeline must produce a dict that exactly matches the
    Layer-1 canonical JSON schema defined in docs/schemas.md.

    Verifies:
    - Top-level keys: proyecto_id, origen, componentes, advertencias,
      requiere_revision
    - Each componente has all required keys with correct types
    - Enum values are valid strings from their respective domains
    - origen is "pdf" (not "skp")
    - classification_method is "llm" (Vision-based classification)
    """
    classify_json = json.dumps({"tipo": "alzado", "confidence": 0.92})
    extract_json = json.dumps(
        {
            "piezas": [
                {
                    "tipo": "puerta",
                    "nombre": "Puerta Cocina",
                    "largo_mm": 700,
                    "ancho_mm": 600,
                    "espesor_mm": 18,
                    "material": "MDF",
                    "cantidad": 1,
                    "confidence": 0.88,
                },
                {
                    "tipo": "lateral",
                    "nombre": "Lateral Izquierdo",
                    "largo_mm": 2400,
                    "ancho_mm": 600,
                    "espesor_mm": 18,
                    "material": "MDF",
                    "cantidad": 2,
                    "confidence": 0.80,
                },
            ]
        }
    )

    agent = _agent_with_mocks(monkeypatch, classify_json, extract_json)
    result = await agent.parse("tests/fixtures/plano_simple.pdf", proyecto_id="proj-pdf-001")

    # ── Top-level structure ────────────────────────────────────────────────
    assert result["proyecto_id"] == "proj-pdf-001"
    assert result["origen"] == "pdf"
    assert isinstance(result["componentes"], list)
    assert isinstance(result["advertencias"], list)
    assert isinstance(result["requiere_revision"], list)
    assert len(result["componentes"]) == 2

    # ── Per-component schema ───────────────────────────────────────────────
    required_keys = {
        "id", "name", "parent", "tipo_inferido", "subtype",
        "dimensiones", "material", "cantidad", "confidence",
        "classification_method",
    }
    valid_tipos = {t.value for t in TipoInferido}
    valid_methods = {m.value for m in ClassificationMethod}

    for comp in result["componentes"]:
        assert required_keys.issubset(comp.keys()), f"Missing keys: {required_keys - comp.keys()}"

        dims = comp["dimensiones"]
        assert set(dims.keys()) == {"largo", "ancho", "espesor"}
        assert all(isinstance(v, float) for v in dims.values())

        assert 0.0 <= comp["confidence"] <= 1.0
        assert comp["tipo_inferido"] in valid_tipos
        assert comp["classification_method"] in valid_methods
        assert comp["classification_method"] == "llm", "PDF parts must use llm method"
        assert isinstance(comp["cantidad"], int) and comp["cantidad"] >= 1

    # ── Spot-check extracted values ────────────────────────────────────────
    by_tipo = {c["tipo_inferido"]: c for c in result["componentes"]}

    puerta = by_tipo["puerta"]
    assert puerta["dimensiones"]["largo"] == pytest.approx(700.0, abs=1.0)
    assert puerta["dimensiones"]["ancho"] == pytest.approx(600.0, abs=1.0)
    assert puerta["dimensiones"]["espesor"] == pytest.approx(18.0, abs=1.0)
    assert puerta["material"] == "MDF"

    lateral = by_tipo["lateral"]
    assert lateral["cantidad"] == 2

    # ── Deduplication sanity ───────────────────────────────────────────────
    # puerta and lateral have different dimension buckets → no merge
    assert len(result["componentes"]) == 2


# ---------------------------------------------------------------------------
# test_consolidate_deduplicates_across_views
# ---------------------------------------------------------------------------


async def test_consolidate_deduplicates_across_views():
    """
    consolidate_parts() must merge parts that appear in multiple views
    (same tipo + ~same dimensions), keeping the highest-confidence entry.
    """
    agent = PDFVisionAgent()

    def _make(tipo, largo, ancho, espesor, conf, page):
        return ExtractedPart(
            id=str(page) + tipo,
            name=tipo,
            tipo_inferido=TipoInferido(tipo),
            largo_mm=largo,
            ancho_mm=ancho,
            espesor_mm=espesor,
            material="MDF",
            cantidad=1,
            confidence=conf,
            page_number=page,
            source_view=PageType.alzado,
        )

    parts = [
        # Same puerta from page 1 (alzado) and page 2 (planta) — dims differ by < 10 mm bucket
        _make("puerta", 700, 600, 18, 0.75, 1),
        _make("puerta", 705, 600, 18, 0.90, 2),  # higher confidence — should win
        # A different lateral
        _make("lateral", 2400, 600, 18, 0.82, 1),
    ]

    consolidated = agent.consolidate_parts(parts)

    assert len(consolidated) == 2  # puerta deduplicated, lateral kept

    puerta = next(p for p in consolidated if p.tipo_inferido == TipoInferido.puerta)
    assert puerta.confidence == pytest.approx(0.90)  # highest-confidence entry kept
    assert puerta.largo_mm == pytest.approx(705.0)   # the winning entry's dims


# ---------------------------------------------------------------------------
# test_markdown_json_parsing
# ---------------------------------------------------------------------------


async def test_markdown_json_parsing(monkeypatch):
    """
    _call_claude_vision responses wrapped in markdown fences must be
    parsed correctly (Claude sometimes wraps JSON in ```json ... ```).
    """
    agent = PDFVisionAgent()
    image = _blank_image()

    fenced_response = '```json\n{"tipo": "planta", "confidence": 0.80}\n```'
    mock_vision = AsyncMock(return_value=fenced_response)
    monkeypatch.setattr(agent, "_call_claude_vision", mock_vision)

    result = await agent.classify_page(image, page_num=1)
    assert result is PageType.planta
