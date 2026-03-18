from collections.abc import AsyncGenerator

from pydantic_settings import BaseSettings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./furniture_estimator.db"
    redis_url: str = "redis://localhost:6379"
    anthropic_api_key: str = ""
    empresa_nombre: str = "Mi Carpintería S.R.L."
    empresa_moneda: str = "USD"
    overhead_pct: float = 0.18
    iva_pct: float = 0.21
    margen_default: float = 0.32
    ml_retrain_every_n: int = 5
    ml_min_samples: int = 20

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
