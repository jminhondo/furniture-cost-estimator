"""
Fixture data for cocina_simple.skp / cocina_simple.pdf tests.

Kitchen design
--------------
  Módulo Bajo 1 (MB1)  60 cm wide, 85 cm tall, 60 cm deep  — 2 puertas, 1 estante
  Módulo Bajo 2 (MB2)  60 cm wide, 85 cm tall, 60 cm deep  — 3 cajones
  Módulo Alto 1 (MA1)  90 cm wide, 220 cm tall, 40 cm deep — 2 puertas, 3 estantes

Totals: 4 puertas, 3 cajones, 4 estantes
Materials: MDF 18mm (structure), HDF 3mm (fondos)

``get_components()`` returns what ``SKPParserAgent._load_raw_components()``
would produce if pyslapi were installed and cocina_simple.skp were parsed.
It is imported lazily to avoid a top-level import of src.agents.skp_parser
(which triggers classifier imports) during collection.
"""

from __future__ import annotations

import json
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent
COCINA_SKP = FIXTURE_DIR / "cocina_simple.skp"
COCINA_PDF = FIXTURE_DIR / "cocina_simple.pdf"


# ---------------------------------------------------------------------------
# Component list (equivalent to pyslapi output)
# ---------------------------------------------------------------------------

def get_components():  # noqa: ANN201
    """Return the COCINA_COMPONENTS list (lazy import of RawComponent)."""
    from src.agents.skp_parser import RawComponent  # noqa: PLC0415

    return [
        # ── Módulo Bajo 1 — 2 puertas, 1 estante ─────────────────────────
        RawComponent("mb1_lat_izq",    "Lateral_Izquierdo_MB1",  "modulo_bajo_1",  850, 580, 18, "MDF 18mm", 1),
        RawComponent("mb1_lat_der",    "Lateral_Derecho_MB1",    "modulo_bajo_1",  850, 580, 18, "MDF 18mm", 1),
        RawComponent("mb1_piso",       "Piso_MB1",               "modulo_bajo_1",  564, 580, 18, "MDF 18mm", 1),
        RawComponent("mb1_techo",      "Techo_MB1",              "modulo_bajo_1",  564, 580, 18, "MDF 18mm", 1),
        RawComponent("mb1_fondo",      "Fondo_MB1",              "modulo_bajo_1",  814, 564,  3, "HDF 3mm",  1),
        RawComponent("mb1_puerta_izq", "Puerta_Izquierda_MB1",   "modulo_bajo_1",  850, 296, 18, "MDF 18mm", 1),
        RawComponent("mb1_puerta_der", "Puerta_Derecha_MB1",     "modulo_bajo_1",  850, 296, 18, "MDF 18mm", 1),
        RawComponent("mb1_estante",    "Entrepaño_MB1",          "modulo_bajo_1",  564, 555, 18, "MDF 18mm", 1),

        # ── Módulo Bajo 2 — 3 cajones ─────────────────────────────────────
        RawComponent("mb2_lat_izq",    "Lateral_Izquierdo_MB2",  "modulo_bajo_2",  850, 580, 18, "MDF 18mm", 1),
        RawComponent("mb2_lat_der",    "Lateral_Derecho_MB2",    "modulo_bajo_2",  850, 580, 18, "MDF 18mm", 1),
        RawComponent("mb2_piso",       "Piso_MB2",               "modulo_bajo_2",  564, 580, 18, "MDF 18mm", 1),
        RawComponent("mb2_techo",      "Techo_MB2",              "modulo_bajo_2",  564, 580, 18, "MDF 18mm", 1),
        RawComponent("mb2_fondo",      "Fondo_MB2",              "modulo_bajo_2",  814, 564,  3, "HDF 3mm",  1),
        # cajon 1
        RawComponent("mb2_cf1",        "Cajon_Frente_1_MB2",     "modulo_bajo_2",  220, 546, 18, "MDF 18mm", 1),
        RawComponent("mb2_cl1",        "Cajon_Lateral_1_MB2",    "modulo_bajo_2",  480, 150, 18, "MDF 18mm", 2),
        # cajon 2
        RawComponent("mb2_cf2",        "Cajon_Frente_2_MB2",     "modulo_bajo_2",  250, 546, 18, "MDF 18mm", 1),
        RawComponent("mb2_cl2",        "Cajon_Lateral_2_MB2",    "modulo_bajo_2",  480, 150, 18, "MDF 18mm", 2),
        # cajon 3
        RawComponent("mb2_cf3",        "Cajon_Frente_3_MB2",     "modulo_bajo_2",  280, 546, 18, "MDF 18mm", 1),
        RawComponent("mb2_cl3",        "Cajon_Lateral_3_MB2",    "modulo_bajo_2",  480, 150, 18, "MDF 18mm", 2),

        # ── Módulo Alto 1 — 2 puertas, 3 estantes ────────────────────────
        RawComponent("ma1_lat_izq",    "Lateral_Izquierdo_MA1",  "modulo_alto_1", 2200, 400, 18, "MDF 18mm", 1),
        RawComponent("ma1_lat_der",    "Lateral_Derecho_MA1",    "modulo_alto_1", 2200, 400, 18, "MDF 18mm", 1),
        RawComponent("ma1_piso",       "Piso_MA1",               "modulo_alto_1",  864, 400, 18, "MDF 18mm", 1),
        RawComponent("ma1_techo",      "Techo_MA1",              "modulo_alto_1",  864, 400, 18, "MDF 18mm", 1),
        RawComponent("ma1_fondo",      "Fondo_MA1",              "modulo_alto_1", 2164, 864,  3, "HDF 3mm",  1),
        RawComponent("ma1_puerta_izq", "Puerta_Izquierda_MA1",   "modulo_alto_1", 2200, 446, 18, "MDF 18mm", 1),
        RawComponent("ma1_puerta_der", "Puerta_Derecha_MA1",     "modulo_alto_1", 2200, 446, 18, "MDF 18mm", 1),
        RawComponent("ma1_e1",         "Entrepaño_1_MA1",        "modulo_alto_1",  864, 375, 18, "MDF 18mm", 1),
        RawComponent("ma1_e2",         "Entrepaño_2_MA1",        "modulo_alto_1",  864, 375, 18, "MDF 18mm", 1),
        RawComponent("ma1_e3",         "Entrepaño_3_MA1",        "modulo_alto_1",  864, 375, 18, "MDF 18mm", 1),
    ]


# ---------------------------------------------------------------------------
# Layer-2 fixture for 10-module kitchen (test 4)
# ---------------------------------------------------------------------------

def build_layer2_10_modulos() -> dict:
    """
    Pre-built Layer-2 JSON representing a 10-module standard kitchen.

    Each module: 2 laterals, piso, techo, fondo, 2 puertas, entrepaño, cajon_frente.
    Used for cost range validation without running the full pipeline.
    """
    pieces_mdf: list[dict] = []
    pieces_hdf: list[dict] = []

    for i in range(10):
        tag = f"m{i:02d}"
        tnum = i  # each module on its own board (simplification)
        pieces_mdf += [
            {"pieza_id": f"{tag}_lat_izq", "nombre": f"Lateral_Izq_{tag}",    "tablero_num": tnum, "x_mm": 0,   "y_mm": 0,   "largo_mm": 850, "ancho_mm": 580, "rotada": False},
            {"pieza_id": f"{tag}_lat_der", "nombre": f"Lateral_Der_{tag}",    "tablero_num": tnum, "x_mm": 600, "y_mm": 0,   "largo_mm": 850, "ancho_mm": 580, "rotada": False},
            {"pieza_id": f"{tag}_piso",    "nombre": f"Piso_{tag}",            "tablero_num": tnum, "x_mm": 0,   "y_mm": 860, "largo_mm": 564, "ancho_mm": 580, "rotada": False},
            {"pieza_id": f"{tag}_techo",   "nombre": f"Techo_{tag}",           "tablero_num": tnum, "x_mm": 600, "y_mm": 860, "largo_mm": 564, "ancho_mm": 580, "rotada": False},
            {"pieza_id": f"{tag}_puerta_izq", "nombre": f"Puerta_Izq_{tag}",  "tablero_num": tnum, "x_mm": 0,   "y_mm": 0,   "largo_mm": 850, "ancho_mm": 296, "rotada": False},
            {"pieza_id": f"{tag}_puerta_der", "nombre": f"Puerta_Der_{tag}",  "tablero_num": tnum, "x_mm": 300, "y_mm": 0,   "largo_mm": 850, "ancho_mm": 296, "rotada": False},
            {"pieza_id": f"{tag}_estante",    "nombre": f"Entrepaño_{tag}",    "tablero_num": tnum, "x_mm": 0,   "y_mm": 910, "largo_mm": 564, "ancho_mm": 555, "rotada": False},
            {"pieza_id": f"{tag}_cfrente",    "nombre": f"Cajon_Frente_{tag}", "tablero_num": tnum, "x_mm": 600, "y_mm": 910, "largo_mm": 220, "ancho_mm": 546, "rotada": False},
        ]
        pieces_hdf.append({
            "pieza_id": f"{tag}_fondo", "nombre": f"Fondo_{tag}",
            "tablero_num": i // 5, "x_mm": 0, "y_mm": 0, "largo_mm": 814, "ancho_mm": 564, "rotada": False,
        })

    # Sheet costs
    mdf_cost = round(10 * (2.750 * 1.830) * 12.50, 2)   # 10 boards
    hdf_cost = round(2  * (2.440 * 1.220) * 5.50,  2)   # 2 boards

    return {
        "proyecto_id": "test_10_modulos",
        "tableros": [
            {
                "material_id": "mdf_18",
                "tableros_necesarios": 10,
                "costo_tableros_usd": mdf_cost,
                "desperdicio_pct": 0.12,
                "plan_de_corte": pieces_mdf,
            },
            {
                "material_id": "hdf_3",
                "tableros_necesarios": 2,
                "costo_tableros_usd": hdf_cost,
                "desperdicio_pct": 0.15,
                "plan_de_corte": pieces_hdf,
            },
        ],
        "herrajes": {
            "lineas": [
                {"herraje_id": "bisagra_blum_110",    "nombre": "Bisagra Blum 110°",        "cantidad": 40,   "precio_unitario_usd": 4.50,  "precio_total_usd": 180.00, "unidad": "u"},
                {"herraje_id": "corredera_blum_500",  "nombre": "Corredera Blum 500mm",    "cantidad": 10,   "precio_unitario_usd": 18.00, "precio_total_usd": 180.00, "unidad": "par"},
                {"herraje_id": "canto_pvc",           "nombre": "Canto PVC 0.4mm",         "cantidad": 85.0, "precio_unitario_usd": 0.85,  "precio_total_usd": 72.25,  "unidad": "ml"},
            ],
            "total_herrajes_usd": 432.25,
        },
        "resumen": {
            "total_materiales_usd": round(mdf_cost + hdf_cost, 2),
            "piezas_procesadas": 90,
        },
    }


# ---------------------------------------------------------------------------
# PDF fixture generator
# ---------------------------------------------------------------------------

def create_cocina_pdf(output_path: Path) -> None:
    """
    Generate a front-elevation (alzado frontal) drawing of the kitchen
    with dimension annotations (cotas).  Requires reportlab.
    """
    from reportlab.lib.pagesizes import A3               # noqa: PLC0415
    from reportlab.lib.units import cm                   # noqa: PLC0415
    from reportlab.pdfgen import canvas as pdfcanvas     # noqa: PLC0415

    W, H = A3
    c = pdfcanvas.Canvas(str(output_path), pagesize=A3)

    # ── Title block ──────────────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 14)
    c.drawString(2 * cm, H - 2 * cm, "COCINA SIMPLE — ALZADO FRONTAL")
    c.setFont("Helvetica", 9)
    c.drawString(2 * cm, H - 2.7 * cm, "Escala 1:20  |  MDF 18mm (estructura)  /  HDF 3mm (fondos)")
    c.setFont("Helvetica", 7)
    c.drawString(2 * cm, H - 3.2 * cm, f"Archivo: cocina_simple.skp  |  Proyecto: Cocina Simple Test")

    # ── Drawing scale: 1 cm paper = 10 cm real ───────────────────────────
    SCALE = 0.1   # paper_mm = real_mm * SCALE
    OX = 3 * cm   # origin X
    OY = 5 * cm   # origin Y (bottom of modules)

    def pw(real_mm: float) -> float:  # paper width/height
        return real_mm * SCALE * cm

    # ── Module Bajo 1 (0–600 mm, h=850 mm) ───────────────────────────────
    mb1_x, mb1_w, mb1_h = OX, pw(600), pw(850)
    c.rect(mb1_x, OY, mb1_w, mb1_h)
    c.setFont("Helvetica-Bold", 7)
    c.drawString(mb1_x + 0.2 * cm, OY + mb1_h / 2, "MB1")
    c.setFont("Helvetica", 6)
    c.drawString(mb1_x + 0.2 * cm, OY + 0.3 * cm, "MDF 18mm")
    # Door divider
    c.line(mb1_x + mb1_w / 2, OY, mb1_x + mb1_w / 2, OY + mb1_h)
    # Width cota
    _draw_cota_h(c, mb1_x, OY - 0.7 * cm, mb1_x + mb1_w, "60 cm")
    # Height cota
    _draw_cota_v(c, mb1_x - 0.7 * cm, OY, OY + mb1_h, "85 cm")

    # ── Module Bajo 2 (600–1200 mm, h=850 mm, 3 drawers) ─────────────────
    mb2_x = mb1_x + mb1_w
    mb2_w, mb2_h = pw(600), pw(850)
    c.rect(mb2_x, OY, mb2_w, mb2_h)
    c.setFont("Helvetica-Bold", 7)
    c.drawString(mb2_x + 0.2 * cm, OY + mb2_h / 2, "MB2")
    c.setFont("Helvetica", 6)
    c.drawString(mb2_x + 0.2 * cm, OY + 0.3 * cm, "3 cajones")
    # Drawer lines (3 equal drawers)
    for k in (1, 2):
        y_line = OY + mb2_h * k / 3
        c.line(mb2_x, y_line, mb2_x + mb2_w, y_line)
    _draw_cota_h(c, mb2_x, OY - 0.7 * cm, mb2_x + mb2_w, "60 cm")

    # ── Module Alto 1 (1200–2100 mm, h=2200 mm) ──────────────────────────
    ma1_x = mb2_x + mb2_w
    ma1_w, ma1_h = pw(900), pw(2200)
    c.rect(ma1_x, OY, ma1_w, ma1_h)
    c.setFont("Helvetica-Bold", 7)
    c.drawString(ma1_x + 0.2 * cm, OY + ma1_h / 2, "MA1")
    c.setFont("Helvetica", 6)
    c.drawString(ma1_x + 0.2 * cm, OY + 0.3 * cm, "MDF 18mm")
    # Door divider
    c.line(ma1_x + ma1_w / 2, OY, ma1_x + ma1_w / 2, OY + ma1_h)
    # Shelf lines (3 shelves)
    for k in (1, 2, 3):
        y_line = OY + ma1_h * k / 4
        c.line(ma1_x, y_line, ma1_x + ma1_w, y_line)
    _draw_cota_h(c, ma1_x, OY - 0.7 * cm, ma1_x + ma1_w, "90 cm")
    _draw_cota_v(c, ma1_x + ma1_w + 0.4 * cm, OY, OY + ma1_h, "220 cm")

    # ── Total width cota ─────────────────────────────────────────────────
    c.setFont("Helvetica", 6)
    _draw_cota_h(c, mb1_x, OY - 1.4 * cm, ma1_x + ma1_w, "210 cm total")

    # ── Material legend ──────────────────────────────────────────────────
    legend_x, legend_y = OX, OY + max(mb1_h, ma1_h) + 0.5 * cm
    c.setFont("Helvetica-Bold", 7)
    c.drawString(legend_x, legend_y, "MATERIALES:")
    c.setFont("Helvetica", 7)
    c.drawString(legend_x, legend_y - 0.4 * cm, "• Estructura: MDF 18mm  (tablero 2750×1830mm, $12.50/m²)")
    c.drawString(legend_x, legend_y - 0.8 * cm, "• Fondos:     HDF 3mm   (tablero 2440×1220mm, $5.50/m²)")
    c.drawString(legend_x, legend_y - 1.2 * cm, "• Herrajes:   Bisagras Blum 110° / Correderas Blum 45kg / Canto PVC 0.4mm")

    c.save()


def _draw_cota_h(c, x1: float, y: float, x2: float, label: str) -> None:
    """Draw a horizontal dimension line with label."""
    c.setFont("Helvetica", 6)
    c.line(x1, y, x2, y)
    c.line(x1, y - 0.15 * __import__("reportlab").lib.units.cm,
           x1, y + 0.15 * __import__("reportlab").lib.units.cm)
    c.line(x2, y - 0.15 * __import__("reportlab").lib.units.cm,
           x2, y + 0.15 * __import__("reportlab").lib.units.cm)
    c.drawCentredString((x1 + x2) / 2, y - 0.35 * __import__("reportlab").lib.units.cm, label)


def _draw_cota_v(c, x: float, y1: float, y2: float, label: str) -> None:
    """Draw a vertical dimension line with label."""
    from reportlab.lib.units import cm as _cm  # noqa: PLC0415
    c.setFont("Helvetica", 6)
    c.line(x, y1, x, y2)
    c.line(x - 0.15 * _cm, y1, x + 0.15 * _cm, y1)
    c.line(x - 0.15 * _cm, y2, x + 0.15 * _cm, y2)
    c.saveState()
    c.translate(x - 0.5 * _cm, (y1 + y2) / 2)
    c.rotate(90)
    c.drawCentredString(0, 0, label)
    c.restoreState()


# ---------------------------------------------------------------------------
# SKP stub generator
# ---------------------------------------------------------------------------

def create_cocina_skp_stub(output_path: Path) -> None:
    """
    Write a stub .skp file.

    In production this would be generated by pyslapi/SketchUp C SDK.
    Tests monkeypatch SKPParserAgent._load_raw_components to inject
    get_components() directly, making the real file content irrelevant.
    The stub just needs to exist on disk so the parser's file-existence
    check passes.
    """
    stub = (
        b"# FURNITURE_COST_ESTIMATOR_TEST_FIXTURE\n"
        b"# cocina_simple.skp -- stub generated by tests/fixtures/cocina_data.py\n"
        b"# Real .skp requires pyslapi + SketchUp C SDK (not in PyPI)\n"
        b"\x00" * 256
    )
    output_path.write_bytes(stub)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Generating cocina_simple.pdf ...")
    create_cocina_pdf(COCINA_PDF)
    print(f"  → {COCINA_PDF}")

    print("Generating cocina_simple.skp (stub) ...")
    create_cocina_skp_stub(COCINA_SKP)
    print(f"  → {COCINA_SKP}")

    print("Done.")
