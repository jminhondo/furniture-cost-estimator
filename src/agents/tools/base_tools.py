"""
Base abstractions for the ToolBelt pattern — Capa 3.

Classes
-------
EstimationResult   — immutable result from any estimator tool
EstimatorTool      — synchronous ABC (Rules, ML)
AsyncEstimatorTool — asynchronous ABC (LLM)
ToolBelt           — orchestrates Rules → ML → LLM cascade with blending
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Blend weights when both ML and Rules are available and confident
ML_WEIGHT: float = 0.70
RULES_WEIGHT: float = 0.30

# Minimum ML confidence to use ML in the blend (else fall through to LLM)
ML_CONFIDENCE_THRESHOLD: float = 0.60

# Minimum confidence for any result before escalating to LLM
LLM_THRESHOLD: float = 0.60


@dataclass(frozen=True)
class EstimationResult:
    """Immutable cost estimation result from any tool."""

    value_usd: float
    confidence: float          # 0.0–1.0
    source: str                # "rules" | "ml" | "llm" | "blend"
    interval_low: float = 0.0
    interval_high: float = 0.0
    explanation: str = ""

    def with_interval(self, low: float, high: float) -> EstimationResult:
        return EstimationResult(
            value_usd=self.value_usd,
            confidence=self.confidence,
            source=self.source,
            interval_low=low,
            interval_high=high,
            explanation=self.explanation,
        )


class EstimatorTool(ABC):
    """Synchronous estimator tool (Rules or ML)."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this tool can produce a result."""

    @abstractmethod
    def estimate(self, features: dict) -> EstimationResult:
        """Produce an EstimationResult for the given feature dict."""


class AsyncEstimatorTool(ABC):
    """Asynchronous estimator tool (LLM)."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this tool can produce a result."""

    @abstractmethod
    async def estimate(self, features: dict) -> EstimationResult:
        """Produce an EstimationResult for the given feature dict."""


class ToolBelt:
    """
    Orchestrate a Rules → ML → LLM cascade with optional blending.

    Cascade logic
    -------------
    1. If ML is available and confident (≥ ML_CONFIDENCE_THRESHOLD):
       - If Rules is also available: blend ML×0.70 + Rules×0.30
       - Else: return ML result directly
    2. If Rules is available (ML not confident / not available):
       - If confidence ≥ LLM_THRESHOLD: return Rules result
       - Else: escalate to LLM (if available)
    3. If LLM available: return LLM result
    4. Fallback: best available result (ML if present, then Rules)

    Parameters
    ----------
    rules_tool:
        Synchronous rules-based estimator (always provided).
    ml_tool:
        Optional synchronous ML estimator.
    llm_tool:
        Optional async LLM estimator.
    """

    def __init__(
        self,
        rules_tool: EstimatorTool,
        ml_tool: EstimatorTool | None = None,
        llm_tool: AsyncEstimatorTool | None = None,
    ) -> None:
        self._rules = rules_tool
        self._ml = ml_tool
        self._llm = llm_tool

    async def run(self, features: dict) -> EstimationResult:
        """Run the cascade and return the best EstimationResult."""
        rules_result: EstimationResult | None = None
        ml_result: EstimationResult | None = None

        # ── Rules ────────────────────────────────────────────────────────
        if self._rules.is_available():
            try:
                rules_result = self._rules.estimate(features)
                logger.debug("Rules estimate: $%.2f (conf=%.2f)", rules_result.value_usd, rules_result.confidence)
            except Exception:
                logger.exception("Rules tool failed")

        # ── ML ───────────────────────────────────────────────────────────
        if self._ml is not None and self._ml.is_available():
            try:
                ml_result = self._ml.estimate(features)
                logger.debug("ML estimate: $%.2f (conf=%.2f)", ml_result.value_usd, ml_result.confidence)
            except Exception:
                logger.exception("ML tool failed")

        # ── Decision tree ─────────────────────────────────────────────────
        if ml_result is not None and ml_result.confidence >= ML_CONFIDENCE_THRESHOLD:
            if rules_result is not None:
                # Blend ML + Rules
                blended = (
                    ML_WEIGHT * ml_result.value_usd
                    + RULES_WEIGHT * rules_result.value_usd
                )
                blended_conf = (
                    ML_WEIGHT * ml_result.confidence
                    + RULES_WEIGHT * rules_result.confidence
                )
                result = EstimationResult(
                    value_usd=round(blended, 2),
                    confidence=round(blended_conf, 4),
                    source="blend",
                    interval_low=min(ml_result.interval_low, rules_result.value_usd * 0.90),
                    interval_high=max(ml_result.interval_high, rules_result.value_usd * 1.10),
                    explanation=f"Blend ML×{ML_WEIGHT} + Rules×{RULES_WEIGHT}",
                )
                logger.debug("Blend result: $%.2f (conf=%.2f)", result.value_usd, result.confidence)
                return result
            else:
                return ml_result

        # ML not confident enough — try rules alone
        if rules_result is not None:
            if rules_result.confidence >= LLM_THRESHOLD:
                return rules_result
            # Rules not confident enough — escalate to LLM

        # ── LLM fallback ─────────────────────────────────────────────────
        if self._llm is not None and self._llm.is_available():
            try:
                llm_result = await self._llm.estimate(features)
                logger.debug("LLM estimate: $%.2f (conf=%.2f)", llm_result.value_usd, llm_result.confidence)
                return llm_result
            except Exception:
                logger.exception("LLM tool failed")

        # ── Last resort: return whatever we have ──────────────────────────
        if ml_result is not None:
            return ml_result
        if rules_result is not None:
            return rules_result

        # Nothing worked — return a zero result
        logger.error("ToolBelt: all tools failed, returning zero estimate")
        return EstimationResult(
            value_usd=0.0,
            confidence=0.0,
            source="none",
            explanation="All estimation tools failed",
        )
