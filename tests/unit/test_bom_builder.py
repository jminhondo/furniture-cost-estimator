"""
Unit tests for Layer-2 BOM Builder and its three sub-agents.

All tests use a minimal in-memory config dict so they are:
  - hermetic (no filesystem reads during the test)
  - fast (no I/O, no network)

Fixture: KITCHEN_L1 — a typical Layer-1 JSON for a simple kitchen cabinet:
  2 × lateral      MDF 18mm  2400×600×18
  1 × fondo        HDF 3mm   2400×1800×3
  1 × techo        MDF 18mm  1800×600×18
  2 × puerta       MDF 18mm  2100×450×18   altura > 1600 → 4 bisagras each
  1 × entrepaño    MDF 18mm  550×600×18
  2 × cajon_frente MDF 18mm  200×400×18    (sibling cajon_lateral depth=500mm)
  2 × cajon_lateral MDF 18mm 500×180×18
"""
from __future__ import annotations

import pytest

from src.agents.cut_optimizer import CutOptimizer
from src.agents.hardware_matcher import HardwareMatcher
from src.agents.material_grouper import MaterialGrouper
from src.layers.layer2_bom import BOMBuilder

# ---------------------------------------------------------------------------
# Minimal config dict (avoids YAML file I/O in tests)
# ---------------------------------------------------------------------------

TEST_CONFIG = {
    "materiales": {
        "mdf_18": {
            "id": "mdf_18",
            "nombre": "MDF 18mm",
            "espesor_mm": 18,
            "precio_usd_m2": 12.50,
            "hoja_largo_mm": 2750,
            "hoja_ancho_mm": 1830,
            "aliases": ["mdf", "mdf 18mm", "melamina", "sin_material"],
        },
        "hdf_3": {
            "id": "hdf_3",
            "nombre": "HDF 3mm",
            "espesor_mm": 3,
            "precio_usd_m2": 5.50,
            "hoja_largo_mm": 2750,   # larger sheet so fondo 2400×1800 fits
            "hoja_ancho_mm": 1830,
            "aliases": ["hdf", "hdf 3mm", "hardboard"],
        },
    },
    "material_default": "mdf_18",
    "corte": {"kerf_mm": 3},
    "canto": {
        "precio_usd_ml": 0.85,
        "tipos_que_llevan_canto": ["puerta", "lateral", "techo", "piso", "entrepaño", "cajon_frente"],
    },
    "herrajes": {
        "bisagra_blum_110": {
            "id": "bisagra_blum_110",
            "nombre": "Bisagra Blum 110°",
            "precio_usd": 4.50,
            "unidad": "u",
        },
        "corredera_blum_400": {
            "id": "corredera_blum_400",
            "nombre": "Corredera Blum 400mm",
            "precio_usd": 16.00,
            "unidad": "par",
        },
        "corredera_blum_500": {
            "id": "corredera_blum_500",
            "nombre": "Corredera Blum 500mm",
            "precio_usd": 18.00,
            "unidad": "par",
        },
        "corredera_blum_600": {
            "id": "corredera_blum_600",
            "nombre": "Corredera Blum 600mm",
            "precio_usd": 22.00,
            "unidad": "par",
        },
    },
    "reglas_herrajes": {
        "bisagras_por_puerta": [
            {"max_altura_mm": 1000, "cantidad": 2, "herraje_id": "bisagra_blum_110"},
            {"max_altura_mm": 1600, "cantidad": 3, "herraje_id": "bisagra_blum_110"},
            {"max_altura_mm": 9999, "cantidad": 4, "herraje_id": "bisagra_blum_110"},
        ],
        "correderas_por_cajon": [
            {"max_profundidad_mm": 450, "herraje_id": "corredera_blum_400"},
            {"max_profundidad_mm": 550, "herraje_id": "corredera_blum_500"},
            {"max_profundidad_mm": 9999, "herraje_id": "corredera_blum_600"},
        ],
        "profundidad_cajon_default_mm": 500,
    },
}

# ---------------------------------------------------------------------------
# Layer-1 fixture JSON
# ---------------------------------------------------------------------------

def _make_comp(id_, name, tipo, largo, ancho, espesor, material, cantidad, parent=None):
    return {
        "id": id_,
        "name": name,
        "parent": parent,
        "tipo_inferido": tipo,
        "subtype": None,
        "dimensiones": {"largo": float(largo), "ancho": float(ancho), "espesor": float(espesor)},
        "material": material,
        "cantidad": cantidad,
        "confidence": 0.90,
        "classification_method": "name_match",
    }


KITCHEN_L1 = {
    "proyecto_id": "cocina-test-001",
    "origen": "skp",
    "componentes": [
        _make_comp("lat-izq",  "lateral_izquierdo", "lateral",     2400, 600,  18, "MDF",     2),
        _make_comp("fondo",    "fondo",              "fondo",       2400, 1800, 3,  "HDF",     1),
        _make_comp("techo",    "techo",              "techo",       1800, 600,  18, "MDF",     1),
        _make_comp("puerta-l", "puerta_izquierda",  "puerta",      2100, 450,  18, "MDF",     2),
        _make_comp("ent",      "entrepaño",          "entrepaño",   550,  600,  18, "MDF",     1),
        _make_comp("cf-1",     "cajon_frente_1",     "cajon_frente",200,  400,  18, "MDF",     2, parent="caj-grp"),
        _make_comp("cl-1",     "cajon_lateral_1",    "cajon_lateral",500, 180,  18, "MDF",     2, parent="caj-grp"),
    ],
    "advertencias": [],
    "requiere_revision": [],
}


# ---------------------------------------------------------------------------
# test_material_grouper_resolves_aliases
# ---------------------------------------------------------------------------


def test_material_grouper_resolves_aliases():
    """
    resolve_material() must map free-text names to the correct material_id.

    Verified aliases:
      "MDF"       → mdf_18
      "mdf 18mm"  → mdf_18 (case-insensitive)
      "HDF"       → hdf_3
      "hdf 3mm"   → hdf_3
      "sin_material" → mdf_18 (default fallback via alias)
      "unknown_xyz"  → mdf_18 (global default fallback)
    """
    grouper = MaterialGrouper(TEST_CONFIG)

    assert grouper.resolve_material("MDF", 18).id == "mdf_18"
    assert grouper.resolve_material("mdf 18mm", 18).id == "mdf_18"
    assert grouper.resolve_material("HDF", 3).id == "hdf_3"
    assert grouper.resolve_material("hdf 3mm", 3).id == "hdf_3"
    assert grouper.resolve_material("sin_material", 18).id == "mdf_18"
    assert grouper.resolve_material("unknown_xyz", 18).id == "mdf_18"

    # Espesor disambiguation: "MDF" with espesor=18 → mdf_18
    # (only mdf_18 exists in test config, but verifies branch coverage)
    spec = grouper.resolve_material("melamina", 18)
    assert spec.id == "mdf_18"

    # Group returns correct number of unique material buckets
    groups = grouper.group(KITCHEN_L1["componentes"])
    material_ids = {g.material_id for g in groups}
    assert "mdf_18" in material_ids
    assert "hdf_3" in material_ids
    assert len(material_ids) == 2  # MDF + HDF


# ---------------------------------------------------------------------------
# test_cut_optimizer_fits_all_pieces
# ---------------------------------------------------------------------------


def test_cut_optimizer_fits_all_pieces():
    """
    CutOptimizer must place every piece in a plan_de_corte entry.

    Total rects in plan_de_corte must equal sum(cantidad) for all pieces.
    Each piece must reference a valid tablero_num (0-indexed, sequential).
    """
    optimizer = CutOptimizer(TEST_CONFIG)
    grouper = MaterialGrouper(TEST_CONFIG)

    groups = grouper.group(KITCHEN_L1["componentes"])
    mdf_group = next(g for g in groups if g.material_id == "mdf_18")

    result = optimizer.optimize(mdf_group)

    # Count expected individual rects (expanding by cantidad)
    expected_rects = sum(int(p["cantidad"]) for p in mdf_group.piezas)
    assert len(result["plan_de_corte"]) == expected_rects, (
        f"Expected {expected_rects} rects in plan, got {len(result['plan_de_corte'])}"
    )

    # All tablero_num must be ≥ 0 and < tableros_necesarios
    tableros_n = result["tableros_necesarios"]
    assert tableros_n >= 1
    for entry in result["plan_de_corte"]:
        assert 0 <= entry["tablero_num"] < tableros_n, (
            f"tablero_num {entry['tablero_num']} out of range [0, {tableros_n})"
        )

    # HDF group — single fondo piece — must also fit
    hdf_group = next(g for g in groups if g.material_id == "hdf_3")
    hdf_result = optimizer.optimize(hdf_group)
    assert hdf_result["tableros_necesarios"] >= 1
    assert len(hdf_result["plan_de_corte"]) == sum(int(p["cantidad"]) for p in hdf_group.piezas)


# ---------------------------------------------------------------------------
# test_cut_optimizer_calculates_waste
# ---------------------------------------------------------------------------


def test_cut_optimizer_calculates_waste():
    """
    desperdicio_pct must be in [0, 1].

    A contrived small batch that easily fits in one sheet must show > 0 waste
    (unless packing is perfect).  A batch that leaves most of the sheet empty
    must show high waste.
    """
    optimizer = CutOptimizer(TEST_CONFIG)
    grouper = MaterialGrouper(TEST_CONFIG)

    groups = grouper.group(KITCHEN_L1["componentes"])
    mdf_group = next(g for g in groups if g.material_id == "mdf_18")
    result = optimizer.optimize(mdf_group)

    waste = result["desperdicio_pct"]
    assert 0.0 <= waste < 1.0, f"Waste {waste} out of range [0, 1)"

    # A tiny single piece on a big sheet → high waste
    grouper2 = MaterialGrouper(TEST_CONFIG)
    tiny_l1 = {
        "componentes": [
            _make_comp("tiny", "tiny", "entrepaño", 100, 50, 18, "MDF", 1)
        ]
    }
    tiny_groups = grouper2.group(tiny_l1["componentes"])
    tiny_group = tiny_groups[0]
    tiny_result = optimizer.optimize(tiny_group)

    assert tiny_result["tableros_necesarios"] == 1
    assert tiny_result["desperdicio_pct"] > 0.95, (
        f"Expected > 95% waste for tiny piece, got {tiny_result['desperdicio_pct']:.2%}"
    )

    # Verify cost > 0
    assert result["costo_tableros_usd"] > 0
    assert tiny_result["costo_tableros_usd"] > 0


# ---------------------------------------------------------------------------
# test_hardware_matcher_bisagras_por_altura
# ---------------------------------------------------------------------------


def test_hardware_matcher_bisagras_por_altura():
    """
    HardwareMatcher must assign the correct number of hinges based on door height.

    Rules (from TEST_CONFIG):
      height ≤ 1000 mm → 2 bisagras
      height ≤ 1600 mm → 3 bisagras
      height >  1600 mm → 4 bisagras
    """
    matcher = HardwareMatcher(TEST_CONFIG)

    def _bisagras_for(altura, cantidad_puertas=1):
        componentes = [
            _make_comp("p1", "puerta", "puerta", altura, 450, 18, "MDF", cantidad_puertas)
        ]
        result = matcher.match(componentes)
        lineas = {l["herraje_id"]: l for l in result["lineas"]}
        return lineas.get("bisagra_blum_110", {}).get("cantidad", 0)

    assert _bisagras_for(800) == 2   # ≤ 1000 mm → 2 each × 1 door
    assert _bisagras_for(1200) == 3  # ≤ 1600 mm → 3 each
    assert _bisagras_for(2100) == 4  # > 1600 mm → 4 each

    # 2 doors at height 2100 → 8 bisagras total
    assert _bisagras_for(2100, cantidad_puertas=2) == 8

    # Verify cost is correct: 8 × 4.50 = 36.00
    componentes = [_make_comp("p2", "puerta", "puerta", 2100, 450, 18, "MDF", 2)]
    result = matcher.match(componentes)
    lineas = {l["herraje_id"]: l for l in result["lineas"]}
    bisagra_line = lineas["bisagra_blum_110"]
    assert bisagra_line["cantidad"] == 8
    assert bisagra_line["precio_total_usd"] == pytest.approx(36.0)


# ---------------------------------------------------------------------------
# test_hardware_matcher_correderas_por_profundidad
# ---------------------------------------------------------------------------


def test_hardware_matcher_correderas_por_profundidad():
    """
    HardwareMatcher must select the correct drawer slide based on drawer depth.

    The depth is read from a sibling cajon_lateral (same parent).
    Rules (from TEST_CONFIG):
      depth ≤ 450 mm → corredera_blum_400
      depth ≤ 550 mm → corredera_blum_500
      depth >  550 mm → corredera_blum_600
    """
    matcher = HardwareMatcher(TEST_CONFIG)

    def _corredera_id_for(profundidad_mm):
        componentes = [
            _make_comp("cf", "cajon_frente", "cajon_frente", 200, 400, 18, "MDF", 1, parent="grp"),
            _make_comp("cl", "cajon_lateral", "cajon_lateral", profundidad_mm, 180, 18, "MDF", 1, parent="grp"),
        ]
        result = matcher.match(componentes)
        lineas = {l["herraje_id"]: l for l in result["lineas"]}
        # Remove canto_pvc — find the first corredera line
        corredera_ids = [lid for lid in lineas if lid.startswith("corredera")]
        return corredera_ids[0] if corredera_ids else None

    assert _corredera_id_for(400) == "corredera_blum_400"
    assert _corredera_id_for(500) == "corredera_blum_500"
    assert _corredera_id_for(600) == "corredera_blum_600"

    # No cajon_lateral sibling → falls back to default (500mm) → corredera_blum_500
    componentes_no_lateral = [
        _make_comp("cf2", "cajon_frente", "cajon_frente", 200, 400, 18, "MDF", 1, parent="grp2"),
    ]
    result_default = matcher.match(componentes_no_lateral)
    corredera_lineas = [l for l in result_default["lineas"] if l["herraje_id"].startswith("corredera")]
    assert len(corredera_lineas) == 1
    assert corredera_lineas[0]["herraje_id"] == "corredera_blum_500"  # default 500mm depth


# ---------------------------------------------------------------------------
# test_full_bom_from_canonical_json
# ---------------------------------------------------------------------------


def test_full_bom_from_canonical_json():
    """
    Full BOM pipeline from Layer-1 JSON must produce a valid Layer-2 JSON
    that matches the canonical schema (docs/schemas.md).

    Validates:
    - Top-level keys: proyecto_id, tableros, herrajes, resumen
    - Each tablero entry has required fields
    - plan_de_corte entries have required fields
    - herrajes.lineas have required fields
    - resumen totals are positive and consistent
    - No pieces are lost (total rects = total component units)
    """
    builder = BOMBuilder(config=TEST_CONFIG)
    result = builder.build(KITCHEN_L1)

    # ── Top-level schema ──────────────────────────────────────────────────
    assert result["proyecto_id"] == "cocina-test-001"
    assert isinstance(result["tableros"], list)
    assert len(result["tableros"]) >= 1

    # ── Tablero schema ────────────────────────────────────────────────────
    tablero_keys = {"material_id", "tableros_necesarios", "costo_tableros_usd",
                    "desperdicio_pct", "plan_de_corte"}
    for t in result["tableros"]:
        assert tablero_keys.issubset(t.keys()), f"Missing keys: {tablero_keys - t.keys()}"
        assert t["tableros_necesarios"] >= 1
        assert 0.0 <= t["desperdicio_pct"] < 1.0
        assert t["costo_tableros_usd"] > 0

    # ── plan_de_corte schema ──────────────────────────────────────────────
    plan_keys = {"pieza_id", "nombre", "tablero_num", "x_mm", "y_mm", "largo_mm", "ancho_mm"}
    for t in result["tableros"]:
        for entry in t["plan_de_corte"]:
            assert plan_keys.issubset(entry.keys()), f"plan entry missing: {plan_keys - entry.keys()}"
            assert entry["largo_mm"] > 0
            assert entry["ancho_mm"] > 0

    # ── All pieces packed ─────────────────────────────────────────────────
    total_expected_rects = sum(int(c["cantidad"]) for c in KITCHEN_L1["componentes"])
    total_packed = sum(len(t["plan_de_corte"]) for t in result["tableros"])
    assert total_packed == total_expected_rects, (
        f"Expected {total_expected_rects} rects, got {total_packed}"
    )

    # ── Herrajes schema ───────────────────────────────────────────────────
    herrajes = result["herrajes"]
    assert "lineas" in herrajes
    assert "total_herrajes_usd" in herrajes
    assert isinstance(herrajes["lineas"], list)
    assert herrajes["total_herrajes_usd"] >= 0

    linea_keys = {"herraje_id", "nombre", "cantidad", "precio_unitario_usd",
                  "precio_total_usd", "unidad"}
    for linea in herrajes["lineas"]:
        assert linea_keys.issubset(linea.keys()), f"Linea missing: {linea_keys - linea.keys()}"
        assert linea["cantidad"] > 0
        assert linea["precio_total_usd"] >= 0

    # ── Bisagras present (2 puertas × 4 bisagras = 8) ────────────────────
    lineas_by_id = {l["herraje_id"]: l for l in herrajes["lineas"]}
    assert "bisagra_blum_110" in lineas_by_id
    assert lineas_by_id["bisagra_blum_110"]["cantidad"] == 8  # 2 puertas × 4

    # ── Correderas present (2 cajones, depth=500mm → blum_500) ───────────
    assert "corredera_blum_500" in lineas_by_id
    assert lineas_by_id["corredera_blum_500"]["cantidad"] == 2  # 2 cajones

    # ── Canto PVC present ─────────────────────────────────────────────────
    assert "canto_pvc" in lineas_by_id
    assert lineas_by_id["canto_pvc"]["cantidad"] > 0

    # ── Resumen ───────────────────────────────────────────────────────────
    resumen = result["resumen"]
    assert resumen["total_materiales_usd"] > 0
    assert resumen["piezas_procesadas"] == len(KITCHEN_L1["componentes"])

    # total_materiales matches sum of tablero costs
    expected_total = sum(t["costo_tableros_usd"] for t in result["tableros"])
    assert resumen["total_materiales_usd"] == pytest.approx(expected_total, rel=1e-4)
