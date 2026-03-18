"""
Unit tests for the SKP Parser Agent and cascade classifier tools.

pyslapi is NOT available in the test environment.  Tests that exercise the
full parser use ``monkeypatch`` to replace ``_load_raw_components`` with a
function that returns a hard-coded list of RawComponent objects representing
a simple kitchen:

    ┌─────────────────────────────────────────┐
    │  name                  L      A    E mm │
    ├─────────────────────────────────────────┤
    │  lateral_izquierdo  2400    600   18    │
    │  lateral_derecho    2400    600   18    │
    │  fondo              2400   1800    3    │
    │  techo               600   1800   18    │
    │  puerta_izquierda   2100    450   18    │
    │  puerta_derecha     2100    450   18    │
    │  entrepaño           550    200   18    │
    └─────────────────────────────────────────┘
"""

from __future__ import annotations

import pytest

from src.agents.classifier import CascadeClassifier, RawComponent
from src.agents.skp_parser import SKPParserAgent
from src.agents.tools.dimension_tool import DimensionClassifierTool
from src.agents.tools.name_tool import NameClassifierTool
from src.models.project import ClassificationMethod, TipoInferido

# ---------------------------------------------------------------------------
# Shared fixture data — matches the create_kitchen_fixture.py kitchen
# ---------------------------------------------------------------------------

KITCHEN_COMPONENTS: list[RawComponent] = [
    RawComponent(
        id="comp-lat-izq",
        name="lateral_izquierdo",
        parent_id=None,
        largo_mm=2400.0,
        ancho_mm=600.0,
        espesor_mm=18.0,
        material="MDF",
    ),
    RawComponent(
        id="comp-lat-der",
        name="lateral_derecho",
        parent_id=None,
        largo_mm=2400.0,
        ancho_mm=600.0,
        espesor_mm=18.0,
        material="MDF",
    ),
    RawComponent(
        id="comp-fondo",
        name="fondo",
        parent_id=None,
        largo_mm=2400.0,
        ancho_mm=1800.0,
        espesor_mm=3.0,
        material="HDF",
    ),
    RawComponent(
        id="comp-techo",
        name="techo",
        parent_id=None,
        largo_mm=1800.0,
        ancho_mm=600.0,
        espesor_mm=18.0,
        material="MDF",
    ),
    RawComponent(
        id="comp-puerta-izq",
        name="puerta_izquierda",
        parent_id=None,
        largo_mm=2100.0,
        ancho_mm=450.0,
        espesor_mm=18.0,
        material="MDF",
    ),
    RawComponent(
        id="comp-puerta-der",
        name="puerta_derecha",
        parent_id=None,
        largo_mm=2100.0,
        ancho_mm=450.0,
        espesor_mm=18.0,
        material="MDF",
    ),
    RawComponent(
        id="comp-entrepaño",
        name="entrepaño",
        parent_id=None,
        largo_mm=550.0,
        ancho_mm=200.0,
        espesor_mm=18.0,
        material="MDF",
    ),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_parser(monkeypatch, components: list[RawComponent] | None = None) -> SKPParserAgent:
    """Return an SKPParserAgent whose _load_raw_components is mocked."""
    data = components if components is not None else KITCHEN_COMPONENTS
    agent = SKPParserAgent()
    monkeypatch.setattr(agent, "_load_raw_components", lambda _path: data)
    return agent


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_load_model_returns_components(monkeypatch):
    """
    _load_raw_components (mocked) must return the expected number of
    components and each must carry correct dimension and material data.
    """
    agent = _make_parser(monkeypatch)
    components = agent._load_raw_components("tests/fixtures/simple_kitchen.skp")

    assert len(components) == len(KITCHEN_COMPONENTS)

    lateral = next(c for c in components if c.name == "lateral_izquierdo")
    assert lateral.largo_mm == pytest.approx(2400.0)
    assert lateral.ancho_mm == pytest.approx(600.0)
    assert lateral.espesor_mm == pytest.approx(18.0)
    assert lateral.material == "MDF"

    fondo = next(c for c in components if c.name == "fondo")
    assert fondo.espesor_mm == pytest.approx(3.0)


async def test_classify_by_name_puerta():
    """
    NameClassifierTool must identify any component whose name contains
    'puerta' (or 'door', case-insensitive) as TipoInferido.puerta with
    high confidence.
    """
    tool = NameClassifierTool()

    for name in ["Puerta_Derecha", "puerta izquierda", "DOOR_LEFT", "panel_puerta_A"]:
        result = tool.classify(name)
        assert result is not None, f"Expected classification for '{name}'"
        tipo, confidence = result
        assert tipo == TipoInferido.puerta, f"Wrong tipo for '{name}': {tipo}"
        assert confidence >= 0.85, f"Confidence too low for '{name}': {confidence}"

    # Should NOT classify unrelated names as puerta
    assert tool.classify("lateral_izquierdo") is None or \
           tool.classify("lateral_izquierdo")[0] != TipoInferido.puerta


async def test_classify_by_dimensions_lateral():
    """
    DimensionClassifierTool must classify a tall, wide panel (typical
    cabinet side) as TipoInferido.lateral.
    """
    tool = DimensionClassifierTool()

    # Standard cabinet lateral: 2400 × 600 × 18 mm
    result = tool.classify(largo_mm=2400.0, ancho_mm=600.0, espesor_mm=18.0)
    assert result is not None
    tipo, confidence = result
    assert tipo == TipoInferido.lateral
    assert confidence >= 0.75

    # Fondo: very thin panel
    result_fondo = tool.classify(largo_mm=2400.0, ancho_mm=1800.0, espesor_mm=3.0)
    assert result_fondo is not None
    assert result_fondo[0] == TipoInferido.fondo

    # Zocalo: very narrow strip
    result_zocalo = tool.classify(largo_mm=1800.0, ancho_mm=80.0, espesor_mm=18.0)
    assert result_zocalo is not None
    assert result_zocalo[0] == TipoInferido.zocalo


async def test_full_pipeline_returns_canonical_json(monkeypatch):
    """
    Full parse() pipeline must return a dict that validates against the
    Layer-1 canonical JSON schema (docs/schemas.md).

    No LLM tool is configured so classification uses only name and dimension
    rules — all kitchen components should be classified correctly.
    """
    agent = _make_parser(monkeypatch)
    result = await agent.parse("tests/fixtures/simple_kitchen.skp", proyecto_id="test-001")

    # Top-level keys
    assert result["proyecto_id"] == "test-001"
    assert result["origen"] == "skp"
    assert isinstance(result["componentes"], list)
    assert isinstance(result["advertencias"], list)
    assert isinstance(result["requiere_revision"], list)

    assert len(result["componentes"]) == len(KITCHEN_COMPONENTS)

    # Validate each component has the required fields
    required_keys = {
        "id", "name", "parent", "tipo_inferido", "subtype",
        "dimensiones", "material", "cantidad", "confidence",
        "classification_method",
    }
    for comp in result["componentes"]:
        assert required_keys.issubset(comp.keys()), f"Missing keys in {comp}"
        dims = comp["dimensiones"]
        assert {"largo", "ancho", "espesor"} == dims.keys()
        assert 0.0 <= comp["confidence"] <= 1.0
        assert comp["classification_method"] in {m.value for m in ClassificationMethod}
        assert comp["tipo_inferido"] in {t.value for t in TipoInferido}

    # Spot-check specific classifications
    by_name = {c["name"]: c for c in result["componentes"]}

    laterales = [c for c in result["componentes"] if "lateral" in c["name"]]
    assert all(c["tipo_inferido"] == "lateral" for c in laterales), \
        f"Laterals miscategorised: {[c['tipo_inferido'] for c in laterales]}"

    assert by_name["fondo"]["tipo_inferido"] == "fondo"
    assert by_name["techo"]["tipo_inferido"] == "techo"

    puertas = [c for c in result["componentes"] if "puerta" in c["name"]]
    assert all(c["tipo_inferido"] == "puerta" for c in puertas), \
        f"Puertas miscategorised: {[c['tipo_inferido'] for c in puertas]}"

    # Dimensions preserved correctly
    lat = by_name["lateral_izquierdo"]
    assert lat["dimensiones"]["largo"] == pytest.approx(2400.0, abs=0.5)
    assert lat["dimensiones"]["ancho"] == pytest.approx(600.0, abs=0.5)
    assert lat["dimensiones"]["espesor"] == pytest.approx(18.0, abs=0.5)
