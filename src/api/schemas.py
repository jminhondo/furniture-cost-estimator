"""Pydantic schemas for API request/response bodies."""

from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Pipeline — analyze
# ---------------------------------------------------------------------------

class AnalyzeResponse(BaseModel):
    project_id: str
    status: str = "processing"


# ---------------------------------------------------------------------------
# Project status
# ---------------------------------------------------------------------------

class LayerProgress(BaseModel):
    parsing: int = Field(0, ge=0, le=100)
    bom: int = Field(0, ge=0, le=100)
    costs: int = Field(0, ge=0, le=100)
    quoting: int = Field(0, ge=0, le=100)


class ProjectStatusResponse(BaseModel):
    project_id: str
    status: str          # processing | parsing | bom | costs | quoting | done | error
    progress: LayerProgress
    created_at: str
    updated_at: str
    error: str | None = None


# ---------------------------------------------------------------------------
# BOM / Costs / Quote
# ---------------------------------------------------------------------------

class BOMResponse(BaseModel):
    project_id: str
    bom: dict


class CostsResponse(BaseModel):
    project_id: str
    costs: dict


class QuoteFilesResponse(BaseModel):
    project_id: str
    quote_number: str
    files: dict[str, str]   # key → download URL path


# ---------------------------------------------------------------------------
# Close project (register real costs)
# ---------------------------------------------------------------------------

class CloseProjectRequest(BaseModel):
    labor_real: float = Field(..., ge=0)
    install_real: float = Field(..., ge=0)
    transport_real: float = Field(..., ge=0)
    total_real: float = Field(..., ge=0)


class CloseProjectResponse(BaseModel):
    project_id: str
    registered: bool
    retrained: bool


# ---------------------------------------------------------------------------
# Regenerate quote
# ---------------------------------------------------------------------------

class RegenerateRequest(BaseModel):
    mode: str = "both"              # "resumido" | "detallado" | "both"
    precio_override: float | None = None


class RegenerateResponse(BaseModel):
    project_id: str
    quote_number: str
    files: dict[str, str]


# ---------------------------------------------------------------------------
# ML
# ---------------------------------------------------------------------------

class AgentMLStatus(BaseModel):
    model_exists: bool
    n_samples: int
    model_path: str


class MLStatusResponse(BaseModel):
    agents: dict[str, AgentMLStatus]


class MLRetrainResponse(BaseModel):
    triggered: bool
    message: str
