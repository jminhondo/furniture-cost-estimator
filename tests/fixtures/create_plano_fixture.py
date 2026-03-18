"""
Generate tests/fixtures/plano_simple.pdf — a minimal furniture technical drawing.

The PDF shows an elevation view (alzado) of a kitchen door panel:
  - Component: PUERTA COCINA
  - Dimensions: 600 mm (width) × 700 mm (height)
  - Thickness (espesor): 18 mm
  - Material: MDF

Run from the project root:
    python tests/fixtures/create_plano_fixture.py
Or call create_plano_simple(path) from Python.
"""
from __future__ import annotations

import os
from pathlib import Path

DEFAULT_OUTPUT = Path(__file__).parent / "plano_simple.pdf"


def create_plano_simple(output_path: str | Path = DEFAULT_OUTPUT) -> Path:
    """Create a simple one-page technical drawing PDF and return its path."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    page_w, page_h = A4  # 595 x 842 pts
    c = canvas.Canvas(str(output_path), pagesize=A4)

    # ── Title block ────────────────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(page_w / 2, page_h - 35 * mm, "ALZADO — PUERTA COCINA")

    c.setFont("Helvetica", 9)
    c.drawCentredString(page_w / 2, page_h - 42 * mm, "Escala 1:10  |  Proyecto: Cocina Demo")

    c.setStrokeColor(colors.black)
    c.setLineWidth(0.5)
    c.line(20 * mm, page_h - 45 * mm, page_w - 20 * mm, page_h - 45 * mm)

    # ── Door rectangle (scaled: 600 mm → 60 mm on paper at 1:10) ──────────
    rect_w = 60 * mm  # 600 mm at 1:10
    rect_h = 70 * mm  # 700 mm at 1:10
    rect_x = (page_w - rect_w) / 2
    rect_y = page_h / 2 - rect_h / 2 + 10 * mm  # vertically centred-ish

    c.setLineWidth(1.2)
    c.rect(rect_x, rect_y, rect_w, rect_h)

    # Cross-hatch to indicate solid panel
    c.setLineWidth(0.3)
    c.setStrokeColor(colors.lightgrey)
    step = 5 * mm
    for i in range(0, int(rect_w / step) + int(rect_h / step) + 2):
        x0 = rect_x + i * step
        y0 = rect_y
        x1 = rect_x
        y1 = rect_y + i * step
        # clip manually to rectangle area
        if x0 > rect_x + rect_w:
            x0 = rect_x + rect_w
        if y1 > rect_y + rect_h:
            y1 = rect_y + rect_h
        c.line(x0, y0, x1, y1)

    c.setStrokeColor(colors.black)
    c.setLineWidth(1.2)
    c.rect(rect_x, rect_y, rect_w, rect_h)

    # ── Component label ────────────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.black)
    c.drawCentredString(rect_x + rect_w / 2, rect_y + rect_h / 2 + 4 * mm, "PUERTA COCINA")
    c.setFont("Helvetica", 9)
    c.drawCentredString(rect_x + rect_w / 2, rect_y + rect_h / 2 - 4 * mm, "Material: MDF")
    c.drawCentredString(rect_x + rect_w / 2, rect_y + rect_h / 2 - 10 * mm, "e = 18 mm")

    # ── Width dimension line (below rectangle) ─────────────────────────────
    dim_gap = 8 * mm
    c.setLineWidth(0.6)

    # Horizontal dim line
    c.line(rect_x, rect_y - dim_gap, rect_x + rect_w, rect_y - dim_gap)
    # Ticks
    c.line(rect_x, rect_y - dim_gap + 2 * mm, rect_x, rect_y - dim_gap - 2 * mm)
    c.line(rect_x + rect_w, rect_y - dim_gap + 2 * mm, rect_x + rect_w, rect_y - dim_gap - 2 * mm)
    # Arrow-like extension lines
    c.line(rect_x, rect_y, rect_x, rect_y - dim_gap)
    c.line(rect_x + rect_w, rect_y, rect_x + rect_w, rect_y - dim_gap)

    c.setFont("Helvetica", 9)
    c.drawCentredString(rect_x + rect_w / 2, rect_y - dim_gap - 5 * mm, "600 mm")

    # ── Height dimension line (right of rectangle) ─────────────────────────
    dim_gap_r = 8 * mm
    right_x = rect_x + rect_w + dim_gap_r

    c.line(right_x, rect_y, right_x, rect_y + rect_h)
    c.line(right_x - 2 * mm, rect_y, right_x + 2 * mm, rect_y)
    c.line(right_x - 2 * mm, rect_y + rect_h, right_x + 2 * mm, rect_y + rect_h)
    c.line(rect_x + rect_w, rect_y, right_x, rect_y)
    c.line(rect_x + rect_w, rect_y + rect_h, right_x, rect_y + rect_h)

    # Rotated text for height
    c.saveState()
    c.translate(right_x + 5 * mm, rect_y + rect_h / 2)
    c.rotate(90)
    c.drawCentredString(0, 0, "700 mm")
    c.restoreState()

    # ── Material / spec block ──────────────────────────────────────────────
    spec_y = rect_y - 28 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(20 * mm, spec_y, "ESPECIFICACIONES:")
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, spec_y - 5 * mm, "Tipo de pieza: Puerta")
    c.drawString(20 * mm, spec_y - 10 * mm, "Dimensiones: 600 x 700 x 18 mm")
    c.drawString(20 * mm, spec_y - 15 * mm, "Material: MDF melamínico blanco")
    c.drawString(20 * mm, spec_y - 20 * mm, "Cantidad: 1 unidad")
    c.drawString(20 * mm, spec_y - 25 * mm, "Acabado: melamina 0.6 mm ambas caras")

    # ── Title block bottom ─────────────────────────────────────────────────
    tb_y = 15 * mm
    c.setLineWidth(0.5)
    c.rect(20 * mm, tb_y, page_w - 40 * mm, 12 * mm)
    c.setFont("Helvetica", 7)
    c.drawString(22 * mm, tb_y + 7 * mm, "Proyecto: Cocina Demo")
    c.drawString(22 * mm, tb_y + 2 * mm, "Plano: PD-001  |  Rev: 0  |  Fecha: 2026-03-17")
    c.drawCentredString(page_w / 2, tb_y + 4 * mm, "ALZADO FRONTAL — PUERTA COCINA")
    c.drawRightString(page_w - 22 * mm, tb_y + 4 * mm, "Hoja 1/1")

    c.save()
    return output_path


if __name__ == "__main__":
    path = create_plano_simple()
    print(f"Fixture created: {path}")
