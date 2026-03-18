from datetime import datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.models.database import Base
from src.models.project import (
    BOMItem,
    BOMItemTipo,
    ClassificationMethod,
    Component,
    CostBreakdown,
    CutPlan,
    MLTrainingData,
    Project,
    ProjectEstado,
    Quote,
    QuoteEstado,
    TipoInferido,
)

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine):
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


async def test_project_creation(session: AsyncSession):
    project = Project(nombre="Cocina Ramírez", cliente="Juan Ramírez")
    session.add(project)
    await session.commit()
    await session.refresh(project)

    assert project.id is not None
    assert project.estado == ProjectEstado.draft
    assert isinstance(project.created_at, datetime)
    assert project.cliente == "Juan Ramírez"


async def test_project_estado_enum(session: AsyncSession):
    for estado in ProjectEstado:
        p = Project(nombre=f"Proyecto {estado.value}", estado=estado)
        session.add(p)
    await session.commit()

    from sqlalchemy import select
    result = await session.execute(select(Project))
    projects = result.scalars().all()
    estados = {p.estado for p in projects}
    assert estados == set(ProjectEstado)


async def test_component_creation(session: AsyncSession):
    project = Project(nombre="Closet")
    session.add(project)
    await session.flush()

    comp = Component(
        project_id=project.id,
        nombre="Panel lateral izquierdo",
        tipo_inferido=TipoInferido.lateral,
        classification_method=ClassificationMethod.dimension_rule,
        confianza=0.95,
        largo_mm=2400.0,
        ancho_mm=600.0,
        espesor_mm=18.0,
        material="MDF",
        cantidad=2,
    )
    session.add(comp)
    await session.commit()
    await session.refresh(comp)

    assert comp.id is not None
    assert comp.confianza == pytest.approx(0.95)
    assert comp.largo_mm == pytest.approx(2400.0)
    assert comp.tipo_inferido == TipoInferido.lateral
    assert comp.classification_method == ClassificationMethod.dimension_rule


async def test_component_self_referential(session: AsyncSession):
    project = Project(nombre="Mueble TV")
    session.add(project)
    await session.flush()

    parent = Component(project_id=project.id, nombre="Cuerpo principal")
    session.add(parent)
    await session.flush()

    child = Component(project_id=project.id, nombre="Puerta izquierda", parent_id=parent.id)
    session.add(child)
    await session.commit()

    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    result = await session.execute(
        select(Component)
        .where(Component.id == parent.id)
        .options(selectinload(Component.children))
    )
    loaded_parent = result.scalar_one()
    assert len(loaded_parent.children) == 1
    assert loaded_parent.children[0].nombre == "Puerta izquierda"


async def test_bom_item(session: AsyncSession):
    project = Project(nombre="Biblioteca")
    session.add(project)
    await session.flush()

    tablero = BOMItem(
        project_id=project.id,
        tipo=BOMItemTipo.tablero,
        descripcion="Melamina blanca 18mm",
        cantidad=3,
        unidad="plancha",
        precio_unitario_usd=Decimal("45.00"),
        precio_total_usd=Decimal("135.00"),
    )
    herraje = BOMItem(
        project_id=project.id,
        tipo=BOMItemTipo.herraje,
        descripcion="Bisagra Blum 110°",
        cantidad=8,
        unidad="u",
        precio_unitario_usd=Decimal("2.50"),
        precio_total_usd=Decimal("20.00"),
        sku="BLUM-110",
    )
    session.add_all([tablero, herraje])
    await session.commit()
    await session.refresh(tablero)
    await session.refresh(herraje)

    assert tablero.tipo == BOMItemTipo.tablero
    assert tablero.precio_total_usd == Decimal("135.00")
    assert herraje.sku == "BLUM-110"


async def test_cut_plan_jsonb(session: AsyncSession):
    project = Project(nombre="Placard")
    session.add(project)
    await session.flush()

    cortes = [
        {"pieza": "lateral_izq", "x": 0, "y": 0, "w": 600, "h": 2400},
        {"pieza": "lateral_der", "x": 610, "y": 0, "w": 600, "h": 2400},
    ]
    plan = CutPlan(
        project_id=project.id,
        material="MDF 18mm",
        hoja_largo_mm=2750.0,
        hoja_ancho_mm=1830.0,
        kerf_mm=3.5,
        cortes=cortes,
        uso_pct=0.78,
    )
    session.add(plan)
    await session.commit()
    await session.refresh(plan)

    assert isinstance(plan.cortes, list)
    assert len(plan.cortes) == 2
    assert plan.cortes[0]["pieza"] == "lateral_izq"
    assert plan.uso_pct == pytest.approx(0.78)


async def test_cost_breakdown(session: AsyncSession):
    project = Project(nombre="Cocina completa")
    session.add(project)
    await session.flush()

    cb = CostBreakdown(
        project_id=project.id,
        materiales_usd=Decimal("1200.00"),
        herrajes_usd=Decimal("300.00"),
        mano_obra_usd=Decimal("800.00"),
        instalacion_usd=Decimal("200.00"),
        transporte_usd=Decimal("100.00"),
        overhead_usd=Decimal("468.00"),
        subtotal_usd=Decimal("3068.00"),
        margen_pct=0.32,
        precio_sugerido_usd=Decimal("4049.76"),
        confianza_ml=0.87,
        fuente_estimacion="ml",
    )
    session.add(cb)
    await session.commit()
    await session.refresh(cb)

    assert cb.subtotal_usd == Decimal("3068.00")
    assert cb.confianza_ml == pytest.approx(0.87)
    assert cb.fuente_estimacion == "ml"
    assert isinstance(cb.created_at, datetime)


async def test_quote(session: AsyncSession):
    project = Project(nombre="Dormitorio")
    session.add(project)
    await session.flush()

    quote = Quote(
        project_id=project.id,
        numero="Q-2026-001",
        estado=QuoteEstado.enviado,
        total_usd=Decimal("5000.00"),
        iva_pct=0.21,
        total_con_iva_usd=Decimal("6050.00"),
        incluye_detalle=True,
        enviado_at=datetime.now(timezone.utc),
    )
    session.add(quote)
    await session.commit()
    await session.refresh(quote)

    assert quote.numero == "Q-2026-001"
    assert quote.estado == QuoteEstado.enviado
    assert quote.total_con_iva_usd == Decimal("6050.00")
    assert quote.enviado_at is not None


async def test_ml_training_data_jsonb(session: AsyncSession):
    project = Project(nombre="Baño")
    session.add(project)
    await session.flush()

    features = {
        "area_total_m2": 12.5,
        "num_piezas": 24,
        "material_principal": "MDF",
        "tiene_instalacion": True,
    }
    record = MLTrainingData(
        project_id=project.id,
        agente="labor",
        features=features,
        target_usd=Decimal("750.00"),
        prediccion_usd=Decimal("720.00"),
        error_pct=0.04,
        used_in_training=False,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)

    assert isinstance(record.features, dict)
    assert record.features["num_piezas"] == 24
    assert record.error_pct == pytest.approx(0.04)
    assert record.used_in_training is False


async def test_cascade_delete(session: AsyncSession):
    project = Project(nombre="Proyecto cascade")
    session.add(project)
    await session.flush()

    comp = Component(project_id=project.id, nombre="Componente A")
    bom = BOMItem(
        project_id=project.id,
        tipo=BOMItemTipo.tablero,
        descripcion="Tablero",
        cantidad=1,
        unidad="u",
    )
    plan = CutPlan(
        project_id=project.id,
        material="MDF",
        hoja_largo_mm=2750.0,
        hoja_ancho_mm=1830.0,
    )
    session.add_all([comp, bom, plan])
    await session.commit()

    project_id = project.id
    await session.delete(project)
    await session.commit()

    from sqlalchemy import select

    result_comp = await session.execute(
        select(Component).where(Component.project_id == project_id)
    )
    assert result_comp.scalars().all() == []

    result_bom = await session.execute(
        select(BOMItem).where(BOMItem.project_id == project_id)
    )
    assert result_bom.scalars().all() == []

    result_plan = await session.execute(
        select(CutPlan).where(CutPlan.project_id == project_id)
    )
    assert result_plan.scalars().all() == []
