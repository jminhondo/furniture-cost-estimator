"""
ML Training Pipeline — Capa 3.

Collects closed-project data and re-trains all cost agent models whenever
RETRAIN_EVERY_N new projects have been registered since the last training run.

Agents retrained
----------------
- labor     (LaborAgent model)
- install   (InstallAgent model)
- transport (TransportAgent model)
- overhead  (OverheadAgent model)

Data format
-----------
Each closed project is registered as:
    {
        "features": {<feature_name>: value, ...},
        "actuals": {
            "labor_usd": float,
            "install_usd": float,
            "transport_usd": float,
            "overhead_usd": float,
        },
    }

MAPE (Mean Absolute Percentage Error) is logged after each retraining run
for each agent so that model quality can be tracked over time.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path

from src.agents.costs.labor_agent import FEATURE_NAMES as LABOR_FEATURES
from src.agents.costs.install_agent import FEATURE_NAMES as INSTALL_FEATURES
from src.agents.costs.transport_agent import FEATURE_NAMES as TRANSPORT_FEATURES
from src.agents.costs.overhead_agent import FEATURE_NAMES as OVERHEAD_FEATURES
from src.agents.tools.ml_tool import MLEstimatorTool

logger = logging.getLogger(__name__)

RETRAIN_EVERY_N: int = 5

_DEFAULT_MODELS_DIR = Path(__file__).parent.parent.parent.parent / "models"

_AGENTS: list[tuple[str, list[str]]] = [
    ("labor", LABOR_FEATURES),
    ("install", INSTALL_FEATURES),
    ("transport", TRANSPORT_FEATURES),
    ("overhead", OVERHEAD_FEATURES),
]


class MLTrainingPipeline:
    """
    Collect closed-project data and re-train all ML cost models.

    Parameters
    ----------
    models_dir:
        Directory where joblib artifacts are saved.
        Default: ``<project_root>/models/``.
    retrain_every_n:
        Number of new projects required to trigger a re-train.
    """

    def __init__(
        self,
        models_dir: str | Path | None = None,
        retrain_every_n: int = RETRAIN_EVERY_N,
    ) -> None:
        self._models_dir = Path(models_dir) if models_dir else _DEFAULT_MODELS_DIR
        self._retrain_every_n = retrain_every_n
        self._buffer: list[dict] = []   # registered but not yet trained
        self._all_data: list[dict] = []  # full historical dataset

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_closed_project(self, project: dict) -> bool:
        """
        Register a closed project's actual costs for future training.

        Parameters
        ----------
        project:
            Dict with ``"features"`` and ``"actuals"`` keys (see module docstring).

        Returns
        -------
        True if a re-training run was triggered, False otherwise.
        """
        self._buffer.append(project)
        self._all_data.append(project)
        logger.debug(
            "Registered project (buffer=%d, total=%d)",
            len(self._buffer),
            len(self._all_data),
        )

        if len(self._buffer) >= self._retrain_every_n:
            self._retrain_all()
            self._buffer.clear()
            return True

        return False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _retrain_all(self) -> None:
        logger.info(
            "Retraining ML models on %d total projects…", len(self._all_data)
        )
        self._models_dir.mkdir(parents=True, exist_ok=True)

        for agent_name, feature_names in _AGENTS:
            target_key = f"{agent_name}_usd"
            X, y = [], []
            for record in self._all_data:
                actuals = record.get("actuals", {})
                if target_key not in actuals:
                    continue
                X.append(record.get("features", {}))
                y.append(float(actuals[target_key]))

            if len(y) < 2:
                logger.warning(
                    "Not enough data to train '%s' (need ≥2, have %d)",
                    agent_name, len(y),
                )
                continue

            model_path = self._models_dir / f"{agent_name}_gbr.joblib"
            tool = MLEstimatorTool.train(
                model_path=model_path,
                X=X,
                y=y,
                feature_names=feature_names,
            )

            # ── MAPE logging ─────────────────────────────────────────
            mape = self._compute_mape(tool, X, y, feature_names)
            logger.info(
                "Agent '%s' retrained — n=%d, MAPE=%.1f%%",
                agent_name, len(y), mape * 100,
            )

    @staticmethod
    def _compute_mape(
        tool: MLEstimatorTool,
        X: list[dict],
        y: list[float],
        feature_names: list[str],
    ) -> float:
        """Return Mean Absolute Percentage Error on the training set."""
        if not tool.is_available():
            return float("nan")

        errors = []
        for features, actual in zip(X, y):
            if actual == 0:
                continue
            result = tool.estimate(features)
            errors.append(abs(result.value_usd - actual) / abs(actual))

        return sum(errors) / len(errors) if errors else 0.0
