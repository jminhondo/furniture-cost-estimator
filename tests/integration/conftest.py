"""
Shared fixtures for integration tests.

Fixtures
--------
test_config      — loaded defaults.yml as a plain dict
test_db          — aiosqlite in-memory AsyncSession (creates all tables)
cocina_skp_path  — session-scoped stub .skp file (tests/fixtures/cocina_simple.skp)
cocina_pdf_path  — session-scoped .pdf drawing   (tests/fixtures/cocina_simple.pdf)
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import yaml

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_CONFIG_PATH = Path(__file__).parent.parent.parent / "configs" / "defaults.yml"


@pytest.fixture(scope="session")
def test_config() -> dict:
    with _CONFIG_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# ---------------------------------------------------------------------------
# In-memory async DB (aiosqlite)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def test_db():
    """
    Create an in-memory SQLite DB with all SQLAlchemy models applied,
    yield an AsyncSession, then dispose the engine.
    """
    from src.models.database import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


# ---------------------------------------------------------------------------
# Fixture file paths (generated once per test session)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def cocina_skp_path() -> Path:
    """
    Return path to the stub cocina_simple.skp, creating it if needed.
    The actual file content is irrelevant — SKPParserAgent._load_raw_components
    is monkeypatched in tests to return fixture components directly.
    """
    from tests.fixtures.cocina_data import COCINA_SKP, create_cocina_skp_stub

    if not COCINA_SKP.exists():
        create_cocina_skp_stub(COCINA_SKP)
    return COCINA_SKP


@pytest.fixture(scope="session")
def cocina_pdf_path() -> Path:
    """
    Return path to cocina_simple.pdf, generating it with reportlab if needed.
    """
    from tests.fixtures.cocina_data import COCINA_PDF, create_cocina_pdf

    if not COCINA_PDF.exists():
        create_cocina_pdf(COCINA_PDF)
    return COCINA_PDF
