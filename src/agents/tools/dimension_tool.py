"""
Dimension-based component classifier.

Uses espesor (thickness) and aspect ratios to infer component type.
Dimensions must be in millimetres.

Classification logic
--------------------
Inputs are first sorted into (espesor, ancho, largo) where:
  espesor = smallest dimension  (thickness)
  ancho   = middle dimension    (width / depth)
  largo   = largest dimension   (height / length)

Rules (applied in priority order):
  1. espesor ≤ 6 mm                              → fondo   (thin back panel)
  2. ancho ≤ 120 mm  AND  ratio ≥ 10             → zocalo  (very narrow, long strip)
  3. espesor ≤ 25 mm  AND  largo ≥ 600 mm:
       a. ancho ≥ 450 mm  AND  ratio ≥ 3.0       → lateral
       b. ancho <  450 mm  AND  ratio ≥ 2.5       → puerta
       c. ancho ≥ 400 mm  AND  ratio <  2.0       → techo   (horizontal panel)
       d. ratio ≥ 2.5  AND  ancho ≥ 100 mm        → entrepaño (deep shelf)
  4. largo ≥ 200 mm  AND  ancho ≥ 100 mm         → entrepaño (small shelf)
  5. No match                                     → None
"""

from src.models.project import TipoInferido


class DimensionClassifierTool:
    """Classify a component by its physical dimensions (all values in mm)."""

    def classify(
        self, largo_mm: float, ancho_mm: float, espesor_mm: float
    ) -> tuple[TipoInferido, float] | None:
        """
        Accept the three already-sorted dimensions (largo ≥ ancho ≥ espesor)
        and return (TipoInferido, confidence) or None.

        The caller is responsible for sorting: pass the largest as largo_mm,
        middle as ancho_mm, smallest as espesor_mm.
        """
        # Defensive sort in case caller passes unsorted values
        dims = sorted([largo_mm, ancho_mm, espesor_mm])
        espesor = dims[0]
        ancho = dims[1]
        largo = dims[2]

        # Guard: ignore degenerate components (zero/tiny)
        if largo < 10:
            return None

        ratio = largo / ancho if ancho > 0 else float("inf")

        # Rule 1: thin back panel
        if espesor <= 6:
            return TipoInferido.fondo, 0.90

        # Rule 2: zocalo — very narrow, long strip
        if ancho <= 120 and ratio >= 10:
            return TipoInferido.zocalo, 0.85

        # Rules 3-x require standard panel thickness and minimum height
        if espesor <= 25 and largo >= 600:
            # 3a: lateral — wide panel, tall
            if ancho >= 450 and ratio >= 3.0:
                return TipoInferido.lateral, 0.82

            # 3b: puerta — narrow panel, tall
            if ancho < 450 and ratio >= 2.5:
                return TipoInferido.puerta, 0.78

            # 3c: techo / piso — horizontal panel (wide, not so tall)
            if ancho >= 400 and ratio < 2.0:
                return TipoInferido.techo, 0.72

            # 3d: entrepaño — moderate shelf proportions
            if ratio >= 2.5 and ancho >= 100:
                return TipoInferido.entrepaño, 0.68

        # Rule 4: small shelf
        if largo >= 200 and ancho >= 100 and espesor <= 25:
            return TipoInferido.entrepaño, 0.60

        return None
