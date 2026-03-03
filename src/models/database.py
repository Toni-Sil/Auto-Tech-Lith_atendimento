from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from src.config import settings

# Criar engine assíncrona
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True
)

# Criar fábrica de sessões
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

# Classe Base para os modelos
class Base(DeclarativeBase):
    pass

# Dependência para obter sessão do banco
async def get_db():
    async with async_session() as session:
        yield session
