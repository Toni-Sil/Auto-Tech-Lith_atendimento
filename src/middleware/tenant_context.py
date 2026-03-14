"""
TenantContext Middleware — Sprint 1 / SaaS Foundation

Responsabilidades:
1. Extrair tenant_id do JWT, header X-Tenant-ID ou subdomain
2. Armazenar no contextvars (thread/async-safe)
3. Injetar no PostgreSQL via SET LOCAL app.current_tenant
4. Bloquear requests sem tenant válido em rotas protegidas
"""

from __future__ import annotations

import re
from contextvars import ContextVar
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from jose import JWTError, jwt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.database import async_session

# ---------------------------------------------------------------------------
# Context variable — isolado por coroutine/task (async-safe)
# ---------------------------------------------------------------------------
_tenant_id_ctx: ContextVar[Optional[int]] = ContextVar("tenant_id", default=None)


def get_current_tenant_id() -> Optional[int]:
    """Retorna o tenant_id da coroutine atual."""
    return _tenant_id_ctx.get()


def set_current_tenant_id(tenant_id: int) -> None:
    """Define o tenant_id para a coroutine atual."""
    _tenant_id_ctx.set(tenant_id)


# ---------------------------------------------------------------------------
# ASGI Middleware
# ---------------------------------------------------------------------------
class TenantMiddleware:
    """
    Middleware ASGI que resolve tenant_id antes de qualquer handler.

    Ordem de resolução:
    1. Header X-Tenant-ID (uso interno / API keys)
    2. JWT claim `tenant_id`
    3. Subdomain: {slug}.app.domain.com
    """

    def __init__(self, app, public_paths: list[str] | None = None):
        self.app = app
        self.public_paths = public_paths or [
            "/health",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/api/auth/register",
            "/api/auth/login",
            "/api/onboarding",
            "/api/webhooks",  # webhooks usam validação própria
        ]

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        # Rotas públicas não precisam de tenant
        if any(path.startswith(p) for p in self.public_paths):
            await self.app(scope, receive, send)
            return

        tenant_id = await self._resolve_tenant(scope)

        if tenant_id is not None:
            set_current_tenant_id(tenant_id)

        await self.app(scope, receive, send)

        # Limpa após o request
        _tenant_id_ctx.set(None)

    async def _resolve_tenant(self, scope) -> Optional[int]:
        headers = dict(scope.get("headers", []))

        # 1. Header direto
        raw_header = headers.get(b"x-tenant-id")
        if raw_header:
            try:
                return int(raw_header.decode())
            except (ValueError, UnicodeDecodeError):
                pass

        # 2. JWT Bearer token
        auth_header = headers.get(b"authorization", b"").decode()
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                payload = jwt.decode(
                    token,
                    settings.SECRET_KEY,
                    algorithms=[settings.JWT_ALGORITHM],
                )
                tid = payload.get("tenant_id")
                if tid:
                    return int(tid)
            except JWTError:
                pass

        # 3. Subdomain: slug.app.domain / slug.localhost
        host = headers.get(b"host", b"").decode().split(":")[0]
        match = re.match(r"^([a-z0-9-]+)\.(?:app\.|localhost)", host)
        if match:
            slug = match.group(1)
            # Resolve slug → tenant_id via cache ou query
            # (implementação completa usa Redis cache)
            return await self._slug_to_tenant_id(slug)

        return None

    async def _slug_to_tenant_id(self, slug: str) -> Optional[int]:
        """Resolve subdomain slug para tenant_id. Cache Redis recomendado em produção."""
        try:
            async with async_session() as session:
                result = await session.execute(
                    text("SELECT id FROM tenants WHERE subdomain = :slug AND is_active = true"),
                    {"slug": slug},
                )
                row = result.fetchone()
                return row[0] if row else None
        except Exception:
            return None


# ---------------------------------------------------------------------------
# FastAPI Dependency — injeta tenant na sessão do banco
# ---------------------------------------------------------------------------
async def get_tenant_db():
    """
    Dependência FastAPI que:
    1. Obtém sessão async do banco
    2. Injeta SET LOCAL app.current_tenant para RLS
    3. Garante que tenant_id está presente (403 se ausente)

    Uso:
        @router.get("/tickets")
        async def list_tickets(db: AsyncSession = Depends(get_tenant_db)):
            ...
    """
    tenant_id = get_current_tenant_id()

    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant não identificado. Autentique-se com uma conta válida.",
        )

    async with async_session() as session:
        # Injeta o tenant_id no contexto da transação PostgreSQL
        # As políticas RLS usam current_setting('app.current_tenant')
        await session.execute(
            text("SET LOCAL app.current_tenant = :tid"),
            {"tid": str(tenant_id)},
        )
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.commit()


async def get_optional_tenant_db():
    """
    Versão opcional — para rotas que podem ou não ter tenant
    (ex: webhooks públicos que identificam tenant pelo payload).
    """
    tenant_id = get_current_tenant_id()

    async with async_session() as session:
        if tenant_id is not None:
            await session.execute(
                text("SET LOCAL app.current_tenant = :tid"),
                {"tid": str(tenant_id)},
            )
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.commit()
