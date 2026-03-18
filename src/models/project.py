import enum
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _json_column():
    return JSON().with_variant(JSONB(), "postgresql")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ProjectEstado(str, enum.Enum):
    draft = "draft"
    quoted = "quoted"
    confirmed = "confirmed"
    closed = "closed"


class TipoInferido(str, enum.Enum):
    puerta = "puerta"
    lateral = "lateral"
    fondo = "fondo"
    techo = "techo"
    piso = "piso"
    entrepaño = "entrepaño"
    cajon_frente = "cajon_frente"
    cajon_lateral = "cajon_lateral"
    cajon_fondo = "cajon_fondo"
    zocalo = "zocalo"
    otro = "otro"


class ClassificationMethod(str, enum.Enum):
    name_match = "name_match"
    dimension_rule = "dimension_rule"
    ml = "ml"
    llm = "llm"


class BOMItemTipo(str, enum.Enum):
    tablero = "tablero"
    herraje = "herraje"


class QuoteEstado(str, enum.Enum):
    borrador = "borrador"
    enviado = "enviado"
    aceptado = "aceptado"
    rechazado = "rechazado"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    cliente: Mapped[str | None] = mapped_column(String(255))
    estado: Mapped[ProjectEstado] = mapped_column(
        Enum(ProjectEstado, native_enum=False),
        default=ProjectEstado.draft,
        nullable=False,
    )
    archivo_origen: Mapped[str | None] = mapped_column(String(512))
    notas: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=_now_utc)
    updated_at: Mapped[datetime] = mapped_column(default=_now_utc, onupdate=_now_utc)

    components: Mapped[list["Component"]] = relationship(
        "Component", back_populates="project", cascade="all, delete-orphan"
    )
    bom_items: Mapped[list["BOMItem"]] = relationship(
        "BOMItem", back_populates="project", cascade="all, delete-orphan"
    )
    cut_plans: Mapped[list["CutPlan"]] = relationship(
        "CutPlan", back_populates="project", cascade="all, delete-orphan"
    )
    cost_breakdowns: Mapped[list["CostBreakdown"]] = relationship(
        "CostBreakdown", back_populates="project", cascade="all, delete-orphan"
    )
    quotes: Mapped[list["Quote"]] = relationship(
        "Quote", back_populates="project", cascade="all, delete-orphan"
    )
    ml_training_data: Mapped[list["MLTrainingData"]] = relationship(
        "MLTrainingData", back_populates="project", cascade="all, delete-orphan"
    )


class Component(Base):
    __tablename__ = "components"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("components.id"))
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    tipo_inferido: Mapped[TipoInferido | None] = mapped_column(
        Enum(TipoInferido, native_enum=False)
    )
    classification_method: Mapped[ClassificationMethod | None] = mapped_column(
        Enum(ClassificationMethod, native_enum=False)
    )
    confianza: Mapped[float | None] = mapped_column(Float)  # 0.0–1.0
    largo_mm: Mapped[float | None] = mapped_column(Float)  # mm
    ancho_mm: Mapped[float | None] = mapped_column(Float)  # mm
    espesor_mm: Mapped[float | None] = mapped_column(Float)  # mm
    material: Mapped[str | None] = mapped_column(String(100))
    cantidad: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    raw_data: Mapped[dict | None] = mapped_column(_json_column())

    project: Mapped["Project"] = relationship("Project", back_populates="components")
    parent: Mapped["Component | None"] = relationship(
        "Component",
        back_populates="children",
        foreign_keys=[parent_id],
        primaryjoin="Component.parent_id == Component.id",
        remote_side="Component.id",
    )
    children: Mapped[list["Component"]] = relationship(
        "Component",
        back_populates="parent",
        foreign_keys=[parent_id],
        primaryjoin="Component.parent_id == Component.id",
    )


class BOMItem(Base):
    __tablename__ = "bom_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    component_id: Mapped[int | None] = mapped_column(ForeignKey("components.id"))
    tipo: Mapped[BOMItemTipo] = mapped_column(
        Enum(BOMItemTipo, native_enum=False), nullable=False
    )
    descripcion: Mapped[str] = mapped_column(String(255), nullable=False)
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False)
    unidad: Mapped[str] = mapped_column(String(20), default="u", nullable=False)
    precio_unitario_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    precio_total_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    proveedor: Mapped[str | None] = mapped_column(String(255))
    sku: Mapped[str | None] = mapped_column(String(100))

    project: Mapped["Project"] = relationship("Project", back_populates="bom_items")


class CutPlan(Base):
    __tablename__ = "cut_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    material: Mapped[str] = mapped_column(String(100), nullable=False)
    hoja_largo_mm: Mapped[float] = mapped_column(Float, nullable=False)  # mm
    hoja_ancho_mm: Mapped[float] = mapped_column(Float, nullable=False)  # mm
    kerf_mm: Mapped[float] = mapped_column(Float, default=3.0)  # mm
    cortes: Mapped[list | None] = mapped_column(_json_column())  # lista de cortes
    uso_pct: Mapped[float | None] = mapped_column(Float)  # 0.0–1.0

    project: Mapped["Project"] = relationship("Project", back_populates="cut_plans")


class CostBreakdown(Base):
    __tablename__ = "cost_breakdowns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    materiales_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    herrajes_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    mano_obra_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    instalacion_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    transporte_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    overhead_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    subtotal_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    margen_pct: Mapped[float | None] = mapped_column(Float)
    precio_sugerido_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    confianza_ml: Mapped[float | None] = mapped_column(Float)  # 0.0–1.0
    fuente_estimacion: Mapped[str | None] = mapped_column(String(50))  # rules|ml|llm
    created_at: Mapped[datetime] = mapped_column(default=_now_utc)

    project: Mapped["Project"] = relationship("Project", back_populates="cost_breakdowns")


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    numero: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    estado: Mapped[QuoteEstado] = mapped_column(
        Enum(QuoteEstado, native_enum=False),
        default=QuoteEstado.borrador,
        nullable=False,
    )
    total_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    iva_pct: Mapped[float | None] = mapped_column(Float)
    total_con_iva_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    pdf_path: Mapped[str | None] = mapped_column(String(512))
    incluye_detalle: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_now_utc)
    enviado_at: Mapped[datetime | None] = mapped_column(default=None)

    project: Mapped["Project"] = relationship("Project", back_populates="quotes")


class MLTrainingData(Base):
    __tablename__ = "ml_training_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    agente: Mapped[str] = mapped_column(String(50), nullable=False)  # labor|install|...
    features: Mapped[dict | None] = mapped_column(_json_column())
    target_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    prediccion_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    error_pct: Mapped[float | None] = mapped_column(Float)
    used_in_training: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_now_utc)

    project: Mapped["Project"] = relationship("Project", back_populates="ml_training_data")
