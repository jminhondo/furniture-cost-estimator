#!/usr/bin/env python3
"""
Generate tests/fixtures/simple_kitchen.skp programmatically using pyslapi.

This script requires the SketchUp C SDK and pyslapi to be installed:
  https://github.com/martijnberger/pyslapi

Kitchen layout (all dimensions in mm → converted to inches for SketchUp):
  - 2 × Lateral     2400 × 600 × 18 mm   (MDF)
  - 1 × Fondo       2400 × 1800 × 3 mm   (HDF)
  - 1 × Techo       600 × 1800 × 18 mm   (MDF)
  - 2 × Puerta      2100 × 450 × 18 mm   (MDF)
  - 1 × Entrepaño   550 × 1800 × 18 mm   (MDF)

Run from the project root:
  python tests/fixtures/create_kitchen_fixture.py
"""

from __future__ import annotations

import math
import os
import sys

OUTPUT = os.path.join(os.path.dirname(__file__), "simple_kitchen.skp")
MM_TO_INCH = 1.0 / 25.4


def mm(value: float) -> float:
    """Convert millimetres to inches (SketchUp internal unit)."""
    return value * MM_TO_INCH


def add_box(
    entities,
    name: str,
    width_mm: float,
    depth_mm: float,
    height_mm: float,
    x_mm: float = 0.0,
    y_mm: float = 0.0,
    z_mm: float = 0.0,
) -> None:
    """Add a box component to entities at the given offset."""
    import sketchup  # noqa: PLC0415

    defn = entities.model.definitions.add(name)
    defn_entities = defn.entities

    # Build box geometry from 6 faces
    pts = [
        [mm(x_mm), mm(y_mm), mm(z_mm)],
        [mm(x_mm + width_mm), mm(y_mm), mm(z_mm)],
        [mm(x_mm + width_mm), mm(y_mm + depth_mm), mm(z_mm)],
        [mm(x_mm), mm(y_mm + depth_mm), mm(z_mm)],
    ]
    base_face = defn_entities.add_face(pts)
    base_face.pushpull(mm(height_mm))

    transform = sketchup.Transformation.new_translation([0, 0, 0])
    entities.add_instance(defn, transform)


def main() -> None:
    try:
        import sketchup  # noqa: PLC0415
    except ImportError:
        print("ERROR: pyslapi (sketchup package) not installed.", file=sys.stderr)
        print("Build from: https://github.com/martijnberger/pyslapi", file=sys.stderr)
        sys.exit(1)

    model = sketchup.Model.new()
    entities = model.entities

    components = [
        # name,           width,  depth,  height, x_offset
        ("lateral_izquierdo", 18, 600, 2400, 0),
        ("lateral_derecho", 18, 600, 2400, 1818),
        ("fondo", 1800, 3, 2400, 18),
        ("techo", 1800, 600, 18, 18),
        ("puerta_izquierda", 450, 18, 2100, 18),
        ("puerta_derecha", 450, 18, 2100, 18 + 900),
        ("entrepaño", 1800, 550, 18, 18),
    ]

    for name, w, d, h, x in components:
        add_box(entities, name, w, d, h, x_mm=x)

    model.save(OUTPUT)
    model.close()
    print(f"Fixture saved to: {OUTPUT}")


if __name__ == "__main__":
    main()
