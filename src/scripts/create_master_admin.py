"""
Script de seed para criar/resetar o usuario master.
Uso: python -m src.scripts.create_master_admin
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.config import settings
from src.models.admin import AdminUser
from src.models.database import Base
from src.utils.security import get_password_hash

# ── Configuracoes do master ──────────────────────────────────────────────
MASTER_USERNAME = os.getenv("MASTER_USERNAME", "autotechlith.master")
MASTER_PASSWORD = os.getenv("MASTER_PASSWORD", "AutoTech@Master2026!")
MASTER_EMAIL    = os.getenv("MASTER_EMAIL",    "master@autotechlith.com")
MASTER_NAME     = os.getenv("MASTER_NAME",     "Master Admin")
# ────────────────────────────────────────────────────────────────────────


async def ensure_master_admin(session: AsyncSession, reset_password: bool = False):
    """Cria o master admin se nao existir. Se reset_password=True, reseta a senha."""
    existing = await session.scalar(
        select(AdminUser).where(AdminUser.username == MASTER_USERNAME)
    )

    if existing:
        if reset_password:
            existing.password_hash = get_password_hash(MASTER_PASSWORD)
            existing.failed_login_attempts = 0
            existing.locked_until = None
            existing.is_active = True
            await session.commit()
            print(f"[OK] Senha do master '{MASTER_USERNAME}' resetada com sucesso.")
            print(f"     Nova senha: {MASTER_PASSWORD}")
        else:
            print(f"[INFO] Master admin '{MASTER_USERNAME}' ja existe. Use --reset para resetar a senha.")
        return existing

    # Criar novo master admin
    master = AdminUser(
        username=MASTER_USERNAME,
        email=MASTER_EMAIL,
        name=MASTER_NAME,
        password_hash=get_password_hash(MASTER_PASSWORD),
        role="master_admin",
        is_active=True,
        email_verified=True,
        phone_verified=True,
        failed_login_attempts=0,
        tenant_id=None,
    )
    session.add(master)
    await session.commit()
    await session.refresh(master)
    print(f"[OK] Master admin criado com sucesso!")
    print(f"     Username : {MASTER_USERNAME}")
    print(f"     Email    : {MASTER_EMAIL}")
    print(f"     Senha    : {MASTER_PASSWORD}")
    print(f"     Role     : master_admin")
    return master


async def main():
    reset = "--reset" in sys.argv

    engine = create_async_engine(settings.DATABASE_URL, echo=False)

    # Garantir que as tabelas existam
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    AsyncSessionLocal = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with AsyncSessionLocal() as session:
        await ensure_master_admin(session, reset_password=reset)

    await engine.dispose()
    print("[DONE] Script finalizado.")


if __name__ == "__main__":
    asyncio.run(main())
