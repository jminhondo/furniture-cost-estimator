"""
End-to-end integration tests for the furniture cost estimator pipeline.

Tests
-----
1. test_skp_to_quote_completo
   Full SKP → Layer1 → Layer2 → Layer3 → Quote pipeline.
   Verifies canonical JSON at each stage, PDF > 1 KB, Excel with 4 sheets.

2. test_pdf_to_bom
   PDF → Layer1 via PDFVisionAgent (Claude API monkeypatched).
   Verifies ≥ 5 pieces extracted with confidence > 0.6.

3. test_ml_feedback_loop
   Registers 20 synthetic closed projects and verifies that
   MLTrainingPipeline triggers retraining and produces model files on disk.

4. test_costos_dentro_de_rango_razonable
   Pre-built 10-module Layer-2 fed directly into CostEngine.
   Verifies: $1 500 ≤ costo_total ≤ $8 000, labor < 60 % of total,
   precio_sugerido > costo_total.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import openpyxl
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROJECT_PARAMS = {
    "distancia_obra_km": 15,
    "distancia_proveedor_km": 30,
    "n_instaladores": 2,
    "tipo_obra": 0,
    "duracion_proyecto_dias": 5,
    "tiene_lacado": False,
}


def _make_claude_page_type_response(page_type: str = "alzado") -> MagicMock:
    """Return a minimal AsyncAnthropic response stub for page-type classification."""
    msg = MagicMock()
    msg.content = [MagicMock(text=json.dumps({"tipo": page_type}))]
    return msg


def _make_claude_extract_response(parts: list[dict]) -> MagicMock:
    """Return a minimal AsyncAnthropic response stub for part extraction."""
    msg = MagicMock()
    msg.content = [MagicMock(text=json.dumps({"piezas": parts}))]
    return msg


# ---------------------------------------------------------------------------
# Test 1 — SKP → Layer1 → Layer2 → Layer3 → Quote
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_skp_to_quote_completo(test_config, cocina_skp_path, tmp_path):
    """
    Full pipeline from SKP stub through quote generation.

    SKPParserAgent._load_raw_components is monkeypatched to return the
    30-component cocina fixture, avoiding the pyslapi dependency.
    CostEngine is instantiated with use_llm=False to skip LLM calls.
    """
    from tests.fixtures.cocina_data import get_components
    from src.agents.skp_parser import SKPParserAgent
    from src.layers.layer2_bom import BOMBuilder
    from src.layers.layer3_costs import CostEngine
    from src.agents.quote_generator import QuoteGenerator

    # ── Layer 1: SKP → canonical JSON ────────────────────────────────────
    agent = SKPParserAgent()
    agent._load_raw_components = lambda _path: get_components()

    project_id = str(uuid.uuid4())
    layer1 = await agent.parse(str(cocina_skp_path), proyecto_id=project_id)

    assert layer1["proyecto_id"] == project_id
    componentes = layer1["componentes"]
    assert len(componentes) >= 20, f"Expected ≥20 components, got {len(componentes)}"

    # All components should have required fields (SKP parser uses "name" not "nombre")
    required_fields = {"id", "name", "tipo_inferido", "dimensiones", "material", "cantidad", "confidence"}
    for comp in componentes:
        missing = required_fields - comp.keys()
        assert not missing, f"Component '{comp.get('name')}' missing: {missing}"

    # Dimensions should be numeric and non-zero
    for comp in componentes:
        dims = comp["dimensiones"]
        assert dims["largo"] > 0
        assert dims["ancho"] > 0
        assert dims["espesor"] > 0

    # Most components should be classified with high confidence (rules-based, no LLM)
    high_conf = [c for c in componentes if c["confidence"] >= 0.60]
    assert len(high_conf) >= 15, f"Expected ≥15 high-confidence components, got {len(high_conf)}"

    # ── Layer 2: Layer1 → BOM ────────────────────────────────────────────
    bom_builder = BOMBuilder(config=test_config)
    layer2 = bom_builder.build(layer1)

    assert layer2["proyecto_id"] == project_id
    assert "tableros" in layer2
    assert "herrajes" in layer2
    assert "resumen" in layer2

    assert len(layer2["tableros"]) >= 1, "Expected at least one material group"
    for tablero in layer2["tableros"]:
        assert "material_id" in tablero
        assert "tableros_necesarios" in tablero
        assert tablero["tableros_necesarios"] >= 1
        assert "costo_tableros_usd" in tablero
        assert tablero["costo_tableros_usd"] > 0
        assert "plan_de_corte" in tablero
        assert len(tablero["plan_de_corte"]) > 0

    assert "total_herrajes_usd" in layer2["herrajes"]
    assert layer2["resumen"]["piezas_procesadas"] > 0

    # ── Layer 3: BOM → costs ─────────────────────────────────────────────
    cost_engine = CostEngine(config=test_config, use_llm=False)
    layer3 = await cost_engine.estimate(layer2, _PROJECT_PARAMS)

    assert layer3["proyecto_id"] == project_id

    required_l3 = {
        "costo_materiales_usd", "costo_mano_obra_usd", "costo_instalacion_usd",
        "costo_transporte_usd", "costo_indirecto_usd", "costo_directo_usd",
        "costo_total_usd", "precio_sugerido_usd", "confianza_global",
        "fuentes", "intervalos",
    }
    missing_l3 = required_l3 - layer3.keys()
    assert not missing_l3, f"Layer-3 missing fields: {missing_l3}"

    # Basic cost sanity
    assert layer3["costo_total_usd"] > 0
    assert layer3["precio_sugerido_usd"] > layer3["costo_total_usd"]
    assert 0.0 <= layer3["confianza_global"] <= 1.0

    intervals = layer3["intervalos"]
    for key in ("labor_low", "labor_high", "install_low", "install_high",
                "transport_low", "transport_high", "overhead_low", "overhead_high"):
        assert key in intervals, f"Missing interval key: {key}"

    # ── Layer 4: Quote generation ─────────────────────────────────────────
    quote_data = {
        "proyecto_id": project_id,
        "proyecto_nombre": "Cocina Integración Test",
        "cliente": {
            "nombre": "Cliente Test",
            "cliente_id": "CL-TEST-001",
            "direccion_obra": "Av. Test 123",
            "email": "test@test.com",
            "telefono": "123-456",
        },
        "layer2": layer2,
        "layer3": layer3,
    }

    generator = QuoteGenerator(config=test_config, output_dir=tmp_path)
    result = await generator.generate(quote_data)

    # Quote number format
    assert result["quote_number"].startswith("PRES-")

    # Files
    files = result["files"]
    assert "pdf_resumido" in files
    assert "pdf_detallado" in files
    assert "excel" in files

    pdf_resumido = Path(files["pdf_resumido"])
    pdf_detallado = Path(files["pdf_detallado"])
    excel_path = Path(files["excel"])

    assert pdf_resumido.exists(), "pdf_resumido not created"
    assert pdf_detallado.exists(), "pdf_detallado not created"
    assert excel_path.exists(), "excel not created"

    # PDF size > 1 KB
    assert pdf_resumido.stat().st_size > 1024, (
        f"pdf_resumido too small: {pdf_resumido.stat().st_size} bytes"
    )
    assert pdf_detallado.stat().st_size > 1024, (
        f"pdf_detallado too small: {pdf_detallado.stat().st_size} bytes"
    )

    # Excel must have exactly 4 sheets
    wb = openpyxl.load_workbook(excel_path)
    expected_sheets = {"BOM", "Herrajes", "Plan de corte", "Costos"}
    actual_sheets = set(wb.sheetnames)
    assert expected_sheets == actual_sheets, (
        f"Excel sheets mismatch. Expected: {expected_sheets}, got: {actual_sheets}"
    )

    # CRM result present (non-fatal even if endpoint not configured)
    assert "crm" in result
    assert "success" in result["crm"]


# ---------------------------------------------------------------------------
# Test 2 — PDF → Layer1 via PDFVisionAgent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pdf_to_bom(cocina_pdf_path):
    """
    Verify PDFVisionAgent extracts ≥ 5 furniture pieces with confidence > 0.6
    from the cocina_simple.pdf fixture.

    _call_claude_vision is monkeypatched to return canned responses, avoiding
    real Claude API calls and the poppler dependency.
    """
    from src.agents.pdf_vision_agent import PDFVisionAgent, PageType
    from PIL import Image as PILImage

    # Fixture: 8 components matching the 3-module kitchen
    _COCINA_PARTS = [
        {"nombre": "Lateral_Izquierdo_MB1", "tipo_inferido": "lateral",        "largo_mm": 850, "ancho_mm": 580, "espesor_mm": 18, "material": "MDF 18mm", "cantidad": 1, "confidence": 0.92},
        {"nombre": "Lateral_Derecho_MB1",   "tipo_inferido": "lateral",        "largo_mm": 850, "ancho_mm": 580, "espesor_mm": 18, "material": "MDF 18mm", "cantidad": 1, "confidence": 0.91},
        {"nombre": "Piso_MB1",              "tipo_inferido": "piso",           "largo_mm": 564, "ancho_mm": 580, "espesor_mm": 18, "material": "MDF 18mm", "cantidad": 1, "confidence": 0.88},
        {"nombre": "Techo_MB1",             "tipo_inferido": "techo",          "largo_mm": 564, "ancho_mm": 580, "espesor_mm": 18, "material": "MDF 18mm", "cantidad": 1, "confidence": 0.85},
        {"nombre": "Fondo_MB1",             "tipo_inferido": "fondo",          "largo_mm": 814, "ancho_mm": 564, "espesor_mm":  3, "material": "HDF 3mm",  "cantidad": 1, "confidence": 0.83},
        {"nombre": "Puerta_Izquierda_MB1",  "tipo_inferido": "puerta",         "largo_mm": 850, "ancho_mm": 296, "espesor_mm": 18, "material": "MDF 18mm", "cantidad": 1, "confidence": 0.90},
        {"nombre": "Puerta_Derecha_MB1",    "tipo_inferido": "puerta",         "largo_mm": 850, "ancho_mm": 296, "espesor_mm": 18, "material": "MDF 18mm", "cantidad": 1, "confidence": 0.90},
        {"nombre": "Entrepaño_MB1",         "tipo_inferido": "estante",        "largo_mm": 564, "ancho_mm": 555, "espesor_mm": 18, "material": "MDF 18mm", "cantidad": 1, "confidence": 0.87},
    ]

    agent = PDFVisionAgent()

    # --- Monkeypatch pdf_to_images ----------------------------------------
    # Return a single 1×1 white image (content doesn't matter — Claude is mocked)
    dummy_image = PILImage.new("RGB", (100, 100), color="white")
    agent.pdf_to_images = lambda _filepath: [dummy_image]

    # --- Monkeypatch _call_claude_vision ---------------------------------
    call_count = 0

    async def _mock_claude_vision(image, system, user_msg):
        nonlocal call_count
        call_count += 1
        # First call per page = page classification
        if call_count % 2 == 1:
            return json.dumps({"tipo": "alzado"})
        # Second call per page = part extraction
        return json.dumps({"piezas": _COCINA_PARTS})

    agent._call_claude_vision = _mock_claude_vision

    project_id = str(uuid.uuid4())
    layer1 = await agent.parse(str(cocina_pdf_path), proyecto_id=project_id)

    assert layer1["proyecto_id"] == project_id

    componentes = layer1["componentes"]
    assert len(componentes) >= 5, f"Expected ≥5 extracted pieces, got {len(componentes)}"

    high_conf = [c for c in componentes if c["confidence"] > 0.6]
    assert len(high_conf) >= 5, (
        f"Expected ≥5 pieces with confidence > 0.6, got {len(high_conf)}"
    )

    # Verify canonical field presence
    for comp in componentes:
        assert "tipo_inferido" in comp
        assert "dimensiones" in comp
        dims = comp["dimensiones"]
        assert dims["largo"] > 0
        assert dims["ancho"] > 0
        assert dims["espesor"] > 0


# ---------------------------------------------------------------------------
# Test 3 — ML feedback loop
# ---------------------------------------------------------------------------

def test_ml_feedback_loop(tmp_path):
    """
    Register 20 synthetic closed projects and verify:
    - MLTrainingPipeline triggers retraining (returns True on 5th, 10th, 15th, 20th)
    - Model files are created on disk after each retraining run
    - Total data accumulates correctly
    """
    from src.agents.tools.training_pipeline import MLTrainingPipeline, RETRAIN_EVERY_N, _AGENTS

    models_dir = tmp_path / "models"
    pipeline = MLTrainingPipeline(models_dir=models_dir, retrain_every_n=RETRAIN_EVERY_N)

    # Synthetic project data — features match all agent feature sets
    def _make_project(i: int) -> dict:
        n_piezas = 20 + i
        area_m2 = 8.0 + i * 0.3
        return {
            "features": {
                # Labor / install shared
                "n_piezas": n_piezas,
                "n_modulos": 2 + i % 3,
                "n_puertas": 2 + i % 4,
                "n_cajones": 1 + i % 3,
                "n_estantes": 2 + i % 2,
                "area_m2": area_m2,
                "factor_complejidad": 1.2 + i * 0.02,
                "tiene_lacado": i % 2,
                "n_materiales_distintos": 2,
                # Install extra
                "distancia_obra_km": 10 + i,
                "n_instaladores": 2,
                "tipo_obra": 0,
                # Transport extra
                "volumen_m3": area_m2 * 0.018,
                "distancia_proveedor_km": 20 + i,
                # Overhead extra
                "costo_directo_usd": 600 + i * 20,
                "duracion_proyecto_dias": 5 + i % 3,
            },
            "actuals": {
                "labor_usd":     280.0 + i * 8,
                "install_usd":   150.0 + i * 5,
                "transport_usd":  60.0 + i * 2,
                "overhead_usd":  120.0 + i * 4,
            },
        }

    retrain_triggers = []
    for i in range(20):
        project = _make_project(i)
        triggered = pipeline.register_closed_project(project)
        retrain_triggers.append(triggered)

    # Retraining should have been triggered 4 times (at 5, 10, 15, 20)
    trigger_count = sum(retrain_triggers)
    assert trigger_count == 4, (
        f"Expected 4 retraining triggers (every {RETRAIN_EVERY_N}), got {trigger_count}"
    )
    # Specifically at positions 4, 9, 14, 19 (0-indexed)
    for idx in (4, 9, 14, 19):
        assert retrain_triggers[idx], f"Expected retraining at project {idx+1}"

    # All 20 projects accumulated in _all_data
    assert len(pipeline._all_data) == 20

    # Buffer cleared after last retrain
    assert len(pipeline._buffer) == 0

    # Model files created on disk for all 4 agents
    for agent_name, _ in _AGENTS:
        model_path = models_dir / f"{agent_name}_gbr.joblib"
        assert model_path.exists(), f"Model not found: {model_path}"
        assert model_path.stat().st_size > 0, f"Empty model file: {model_path}"

    # Models are loadable via joblib
    import joblib
    for agent_name, _ in _AGENTS:
        model_path = models_dir / f"{agent_name}_gbr.joblib"
        artifact = joblib.load(model_path)
        assert "model" in artifact
        assert "n_samples" in artifact
        assert artifact["n_samples"] >= 2  # trained on all 20 samples


# ---------------------------------------------------------------------------
# Test 4 — Cost ranges for a 10-module kitchen
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_costos_dentro_de_rango_razonable(test_config):
    """
    Feed the pre-built 10-module Layer-2 fixture into CostEngine and verify:
    - costo_total is between $1 500 and $8 000
    - labor cost < 60 % of costo_total
    - precio_sugerido > costo_total
    """
    from tests.fixtures.cocina_data import build_layer2_10_modulos
    from src.layers.layer3_costs import CostEngine

    layer2 = build_layer2_10_modulos()

    cost_engine = CostEngine(config=test_config, use_llm=False)
    layer3 = await cost_engine.estimate(layer2, _PROJECT_PARAMS)

    costo_total = layer3["costo_total_usd"]
    labor = layer3["costo_mano_obra_usd"]
    precio = layer3["precio_sugerido_usd"]

    # ── Range check ───────────────────────────────────────────────────────
    assert costo_total >= 1_500, (
        f"costo_total ${costo_total:.2f} below $1 500 lower bound"
    )
    assert costo_total <= 8_000, (
        f"costo_total ${costo_total:.2f} above $8 000 upper bound"
    )

    # ── Labor ratio ───────────────────────────────────────────────────────
    labor_ratio = labor / costo_total
    assert labor_ratio < 0.60, (
        f"Labor is {labor_ratio:.1%} of total — exceeds 60 % cap"
    )

    # ── Price > cost ──────────────────────────────────────────────────────
    assert precio > costo_total, (
        f"precio_sugerido ${precio:.2f} ≤ costo_total ${costo_total:.2f}"
    )

    # ── Additional schema sanity ──────────────────────────────────────────
    assert layer3["costo_materiales_usd"] > 0
    assert layer3["costo_mano_obra_usd"] > 0
    assert layer3["costo_instalacion_usd"] > 0
    assert layer3["costo_transporte_usd"] > 0
    assert layer3["costo_indirecto_usd"] > 0

    # Direct cost = materials + labor + install + transport
    computed_direct = (
        layer3["costo_materiales_usd"]
        + layer3["costo_mano_obra_usd"]
        + layer3["costo_instalacion_usd"]
        + layer3["costo_transporte_usd"]
    )
    assert abs(layer3["costo_directo_usd"] - computed_direct) < 0.10, (
        f"costo_directo_usd mismatch: {layer3['costo_directo_usd']:.2f} vs computed {computed_direct:.2f}"
    )

    # Total = direct + overhead
    computed_total = layer3["costo_directo_usd"] + layer3["costo_indirecto_usd"]
    assert abs(costo_total - computed_total) < 0.10, (
        f"costo_total_usd mismatch: {costo_total:.2f} vs computed {computed_total:.2f}"
    )
