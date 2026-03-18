"""
Integration tests for the FastAPI application.

Strategy
--------
- ``TestClient`` from ``starlette`` is used so that background tasks
  run synchronously before the response is returned to the caller.
- Redis is replaced with ``FakeRedis`` (in-memory dict) injected via
  ``app.dependency_overrides``.
- ``run_pipeline`` is patched to skip all heavy ML/parsing work and
  write a "done" state to FakeRedis immediately.
- ``MLTrainingPipeline`` is replaced with a ``MagicMock`` to verify
  registration calls without triggering real model I/O.

Tests
-----
1. test_analyze_skp_returns_project_id
2. test_status_polling_reaches_done
3. test_bom_endpoint_returns_canonical_schema
4. test_close_project_triggers_ml_update
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.api.deps import get_redis, get_training_pipeline, get_quote_output_dir


# ---------------------------------------------------------------------------
# Fake Redis
# ---------------------------------------------------------------------------

class FakeRedis:
    """Minimal in-memory Redis replacement for tests."""

    def __init__(self):
        self._store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._store[key] = value

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

MOCK_LAYER2 = {
    "proyecto_id": "test-001",
    "tableros": [
        {
            "material_id": "mdf_18",
            "tableros_necesarios": 3,
            "costo_tableros_usd": 207.56,
            "desperdicio_pct": 0.12,
            "plan_de_corte": [
                {"pieza_id": "p1", "nombre": "Lateral", "tablero_num": 0,
                 "x_mm": 0, "y_mm": 0, "largo_mm": 700.0, "ancho_mm": 400.0, "rotada": False},
            ],
        }
    ],
    "herrajes": {
        "lineas": [
            {"herraje_id": "bisagra_blum_110", "nombre": "Bisagra Blum",
             "cantidad": 4, "precio_unitario_usd": 4.50, "precio_total_usd": 18.00, "unidad": "u"},
        ],
        "total_herrajes_usd": 18.00,
    },
    "resumen": {"total_materiales_usd": 207.56, "piezas_procesadas": 5},
}

MOCK_LAYER3 = {
    "proyecto_id": "test-001",
    "costo_materiales_usd": 225.56,
    "costo_mano_obra_usd": 320.00,
    "costo_instalacion_usd": 180.00,
    "costo_transporte_usd": 85.00,
    "costo_indirecto_usd": 146.00,
    "costo_directo_usd": 810.56,
    "costo_total_usd": 956.56,
    "precio_sugerido_usd": 1520.00,
    "confianza_global": 0.74,
    "fuentes": {"materiales": "bom", "mano_obra": "rules",
                "instalacion": "rules", "transporte": "rules", "indirecto": "rules"},
    "intervalos": {"labor_low": 256.0, "labor_high": 400.0,
                   "install_low": 144.0, "install_high": 234.0,
                   "transport_low": 72.0, "transport_high": 102.0,
                   "overhead_low": 131.0, "overhead_high": 168.0},
}


def _done_state(project_id: str) -> str:
    """Build a JSON state string for a successfully completed project."""
    now = datetime.now(timezone.utc).isoformat()
    return json.dumps({
        "project_id": project_id,
        "status": "done",
        "progress": {"parsing": 100, "bom": 100, "costs": 100, "quoting": 100},
        "file_path": f"/tmp/{project_id}/test.skp",
        "file_type": "skp",
        "metadata": {
            "proyecto_nombre": "Cocina Test",
            "cliente": {"nombre": "Test Client", "cliente_id": "CL-001",
                        "direccion_obra": "Av. Test 1", "email": "t@t.com", "telefono": "000"},
        },
        "layer1": {"proyecto_id": project_id, "componentes": []},
        "layer2": MOCK_LAYER2,
        "layer3": MOCK_LAYER3,
        "layer4": {
            "quote_number": "PRES-202603-0001",
            "files": {
                "pdf_resumido": f"/tmp/quotes/{project_id}/PRES-202603-0001_resumido.pdf",
                "pdf_detallado": f"/tmp/quotes/{project_id}/PRES-202603-0001_detallado.pdf",
                "excel": f"/tmp/quotes/{project_id}/PRES-202603-0001.xlsx",
            },
            "crm": {"success": False, "status_code": None, "error": "no endpoint configured"},
        },
        "error": None,
        "created_at": now,
        "updated_at": now,
    })


@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest.fixture
def mock_training_pipeline():
    mock = MagicMock()
    mock.register_closed_project.return_value = False
    return mock


@pytest.fixture
def client(fake_redis, mock_training_pipeline, tmp_path):
    app = create_app()
    app.dependency_overrides[get_redis] = lambda: fake_redis
    app.dependency_overrides[get_training_pipeline] = lambda: mock_training_pipeline
    app.dependency_overrides[get_quote_output_dir] = lambda: tmp_path

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c, fake_redis, mock_training_pipeline

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Test 1 — POST /analyze returns a project_id
# ---------------------------------------------------------------------------

def test_analyze_skp_returns_project_id(client, tmp_path):
    c, fake_redis, _ = client

    async def _noop_pipeline(*args, **kwargs):
        # Write minimal done state so polling works
        project_id = args[0]
        await fake_redis.set(f"project:{project_id}", _done_state(project_id))

    with patch("src.api.routers.pipeline.run_pipeline", side_effect=_noop_pipeline):
        response = c.post(
            "/api/v1/projects/analyze",
            files={"file": ("cabinet.skp", b"SKP\x00binary", "application/octet-stream")},
            data={"metadata": json.dumps({"proyecto_nombre": "Test cabinet"})},
        )

    assert response.status_code == 202
    body = response.json()
    assert "project_id" in body
    assert body["status"] == "processing"
    assert uuid.UUID(body["project_id"])  # valid UUID


# ---------------------------------------------------------------------------
# Test 2 — Status polling reaches "done" after pipeline completes
# ---------------------------------------------------------------------------

def test_status_polling_reaches_done(client):
    c, fake_redis, _ = client

    async def _mock_pipeline(project_id, *args, **kwargs):
        await fake_redis.set(f"project:{project_id}", _done_state(project_id))

    with patch("src.api.routers.pipeline.run_pipeline", side_effect=_mock_pipeline):
        post_resp = c.post(
            "/api/v1/projects/analyze",
            files={"file": ("plan.skp", b"SKP data", "application/octet-stream")},
            data={"metadata": "{}"},
        )

    assert post_resp.status_code == 202
    project_id = post_resp.json()["project_id"]

    # Background task ran inline (TestClient behaviour) — state is now "done"
    status_resp = c.get(f"/api/v1/projects/{project_id}/status")
    assert status_resp.status_code == 200
    body = status_resp.json()
    assert body["status"] == "done"
    assert body["progress"]["parsing"] == 100
    assert body["progress"]["bom"] == 100
    assert body["progress"]["costs"] == 100
    assert body["progress"]["quoting"] == 100


# ---------------------------------------------------------------------------
# Test 3 — BOM endpoint returns canonical Layer-2 schema
# ---------------------------------------------------------------------------

def test_bom_endpoint_returns_canonical_schema(client):
    c, fake_redis, _ = client

    project_id = str(uuid.uuid4())

    # Inject done state directly — no need to run pipeline
    import anyio
    anyio.from_thread.run_sync(
        lambda: None  # ensure event loop exists; use sync set below
    ) if False else None
    # FakeRedis.set is async; call the sync-compatible internal dict directly
    fake_redis._store[f"project:{project_id}"] = _done_state(project_id)

    response = c.get(f"/api/v1/projects/{project_id}/bom")
    assert response.status_code == 200

    body = response.json()
    assert body["project_id"] == project_id

    bom = body["bom"]
    # Required top-level keys of the Layer-2 canonical schema
    assert "tableros" in bom
    assert "herrajes" in bom
    assert "resumen" in bom

    # At least one tablero with required fields
    assert len(bom["tableros"]) > 0
    tablero = bom["tableros"][0]
    assert "material_id" in tablero
    assert "tableros_necesarios" in tablero
    assert "costo_tableros_usd" in tablero
    assert "plan_de_corte" in tablero

    # Herrajes structure
    assert "lineas" in bom["herrajes"]
    assert "total_herrajes_usd" in bom["herrajes"]


# ---------------------------------------------------------------------------
# Test 4 — POST /close registers costs and calls training pipeline
# ---------------------------------------------------------------------------

def test_close_project_triggers_ml_update(client):
    c, fake_redis, mock_pipeline = client

    project_id = str(uuid.uuid4())
    fake_redis._store[f"project:{project_id}"] = _done_state(project_id)

    response = c.post(
        f"/api/v1/projects/{project_id}/close",
        json={
            "labor_real": 380.0,
            "install_real": 200.0,
            "transport_real": 90.0,
            "total_real": 1100.0,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == project_id
    assert body["registered"] is True

    # Verify the training pipeline was called once with the right structure
    mock_pipeline.register_closed_project.assert_called_once()
    call_arg = mock_pipeline.register_closed_project.call_args[0][0]
    assert "features" in call_arg
    assert "actuals" in call_arg
    assert call_arg["actuals"]["labor_usd"] == 380.0
    assert call_arg["actuals"]["install_usd"] == 200.0
    assert call_arg["actuals"]["transport_usd"] == 90.0


# ---------------------------------------------------------------------------
# Additional: 404 for unknown project
# ---------------------------------------------------------------------------

def test_unknown_project_returns_404(client):
    c, _, _ = client
    response = c.get("/api/v1/projects/nonexistent-id/status")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Additional: invalid file type rejected
# ---------------------------------------------------------------------------

def test_invalid_file_type_rejected(client):
    c, _, _ = client
    response = c.post(
        "/api/v1/projects/analyze",
        files={"file": ("drawing.dwg", b"DXF data", "application/octet-stream")},
        data={"metadata": "{}"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Additional: health endpoint
# ---------------------------------------------------------------------------

def test_health_endpoint(client):
    c, _, _ = client
    response = c.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
