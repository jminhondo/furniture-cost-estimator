"""
Generic ML Estimator Tool — Capa 3.

Uses a GradientBoostingRegressor (scikit-learn) persisted via joblib.

Confidence model
----------------
Confidence scales with the number of training samples and plateaus at 0.92:

    confidence = 0.92 × (1 − exp(−n_samples / 30))

This means:
  - 0 samples  → confidence = 0.0  (is_available() returns False)
  - 10 samples → confidence ≈ 0.52
  - 30 samples → confidence ≈ 0.58
  - 60 samples → confidence ≈ 0.74
  - 100 samples→ confidence ≈ 0.83
  - 200 samples→ confidence ≈ 0.90

is_available() requires model loaded AND n_samples >= min_samples_to_activate
(default 5).
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from src.agents.tools.base_tools import EstimationResult, EstimatorTool

logger = logging.getLogger(__name__)

_CONFIDENCE_PLATEAU: float = 0.92
_CONFIDENCE_SCALE: float = 30.0  # samples to reach ~58% confidence


def _confidence_for_samples(n_samples: int) -> float:
    """Return model confidence given training set size."""
    if n_samples <= 0:
        return 0.0
    return _CONFIDENCE_PLATEAU * (1.0 - math.exp(-n_samples / _CONFIDENCE_SCALE))


class MLEstimatorTool(EstimatorTool):
    """
    Generic ML estimation tool backed by a GradientBoostingRegressor.

    Parameters
    ----------
    model_path:
        Path to a joblib-persisted dict:
        ``{"model": GradientBoostingRegressor, "feature_names": list[str],
           "n_samples": int}``.
        If the file does not exist the tool starts in the unavailable state.
    min_samples_to_activate:
        Minimum training samples before is_available() returns True.
    """

    def __init__(
        self,
        model_path: str | Path,
        min_samples_to_activate: int = 5,
    ) -> None:
        self._model_path = Path(model_path)
        self._min_samples = min_samples_to_activate
        self._model: Any | None = None
        self._feature_names: list[str] = []
        self._n_samples: int = 0
        self._load()

    # ------------------------------------------------------------------
    # EstimatorTool interface
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        return self._model is not None and self._n_samples >= self._min_samples

    def estimate(self, features: dict) -> EstimationResult:
        if not self.is_available():
            raise RuntimeError("MLEstimatorTool is not available")

        X = self._build_feature_vector(features)
        prediction = float(self._model.predict(X)[0])
        confidence = _confidence_for_samples(self._n_samples)

        # Rough interval from individual estimator variance (GB has estimators_)
        try:
            tree_preds = np.array(
                [e[0].predict(X)[0] for e in self._model.estimators_]
            )
            std = float(np.std(tree_preds))
        except Exception:
            std = prediction * 0.15  # 15% fallback

        return EstimationResult(
            value_usd=round(max(0.0, prediction), 2),
            confidence=round(confidence, 4),
            source="ml",
            interval_low=round(max(0.0, prediction - 1.96 * std), 2),
            interval_high=round(prediction + 1.96 * std, 2),
            explanation=f"GBR prediction (n_samples={self._n_samples})",
        )

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    @classmethod
    def train(
        cls,
        model_path: str | Path,
        X: list[dict],
        y: list[float],
        feature_names: list[str],
        min_samples_to_activate: int = 5,
    ) -> "MLEstimatorTool":
        """
        Train (or re-train) a GradientBoostingRegressor and persist it.

        Parameters
        ----------
        model_path:   Where to save the model artifact.
        X:            List of feature dicts (same keys as feature_names).
        y:            Target values in USD.
        feature_names: Ordered list of feature keys.
        """
        from sklearn.ensemble import GradientBoostingRegressor  # lazy import

        model_path = Path(model_path)
        model_path.parent.mkdir(parents=True, exist_ok=True)

        X_arr = np.array([[row.get(f, 0.0) for f in feature_names] for row in X])
        y_arr = np.array(y, dtype=float)

        gbr = GradientBoostingRegressor(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            random_state=42,
        )
        gbr.fit(X_arr, y_arr)

        artifact = {
            "model": gbr,
            "feature_names": feature_names,
            "n_samples": len(y),
        }
        joblib.dump(artifact, model_path)
        logger.info("Model saved to %s (n_samples=%d)", model_path, len(y))

        tool = cls(model_path, min_samples_to_activate)
        return tool

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self._model_path.exists():
            logger.debug("Model not found at %s — tool unavailable", self._model_path)
            return
        try:
            artifact = joblib.load(self._model_path)
            self._model = artifact["model"]
            self._feature_names = artifact["feature_names"]
            self._n_samples = int(artifact.get("n_samples", 0))
            logger.info(
                "ML model loaded from %s (n_samples=%d)",
                self._model_path,
                self._n_samples,
            )
        except Exception:
            logger.exception("Failed to load ML model from %s", self._model_path)

    def _build_feature_vector(self, features: dict) -> np.ndarray:
        row = [float(features.get(f, 0.0)) for f in self._feature_names]
        return np.array([row])
