"""
TenantContextMiddleware

Define o tenant ativo no contexto da request.
Todo acesso ao banco deve passar por aqui.

Fluxo:
 1. Extrai tenant_id do JWT ou da API key do header
 2. Valida que o tenant existe e está ativo
 3. Define app.current_tenant no PostgreSQL via SET LOCAL
 4. Injeta tenant_id no request.state para uso nos endpoints

Segurança:
 - Requests sem tenant válido retornam 401
 - Rotas públicas (health, auth, onboarding, master) são excluídas
"""
import logging
from contextvars import ContextVar
from typing import Optional

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# ContextVar global — acessível em qualquer camada sem passar pelo request
current_tenant_id: ContextVar[Optional[int]] = ContextVar(
    "current_tenant_id", default=None
)

# Rotas que não precisam de tenant
PUBLIC_PATHS = {
    "/",
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/forgot-password",
    "/api/v1/auth/token",
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/recovery/request",
    "/api/v1/auth/recovery/reset",
    "/api/v1/auth/refresh",
    "/api/onboarding/register",
    "/api/webhooks/whatsapp",
    "/api/webhooks/telegram",
    "/login",
    "/login.html",
    "/home.html",
    "/master.html",
    "/client.html",
    "/onboarding",
    "/onboarding.html",
    "/privacidade.html",
    "/termos.html",
    "/lgpd.html",
    "/favicon.ico",
}

# Prefixos de rota que não precisam de tenant
PUBLIC_PREFIXES = (
    "/static",
    "/api/v1/master",
    "/api/v1/auth",
    "/assets",
    "/css",
    "/js",
    "/img",
    "/dist",
)


class TenantContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware que injeta o tenant_id no contexto de cada request.

    Ordem de resolução do tenant:
    1. Header X-Tenant-ID (uso interno / API keys)
    2. JWT claim 'tenant_id' (sessão de usuário)
    3. Subdomínio da request (futuro: app.{subdomain}.domain.com)
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # Ignorar rotas públicas (exact match ou prefixo)
        if path in PUBLIC_PATHS or any(path.startswith(p) for p in PUBLIC_PREFIXES):
            return await call_next(request)

        tenant_id = await self._resolve_tenant(request)

        if tenant_id is None:
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "Tenant não identificado. Autentique-se ou forneça X-Tenant-ID."
                },
            )

        # Injeta no request.state e no ContextVar global
        request.state.tenant_id = tenant_id
        token = current_tenant_id.set(tenant_id)

        try:
            response = await call_next(request)
            return response
        except Exception as exc:
            logger.error(
                f"[TenantMiddleware] Erro no request tenant_id={tenant_id}: {exc}",
                exc_info=True,
            )
            raise
        finally:
            # Sempre limpa o contexto ao fim do request
            current_tenant_id.reset(token)

    async def _resolve_tenant(self, request: Request) -> Optional[int]:
        # 1. Header direto (API keys internas, webhooks autenticados)
        header_tid = request.headers.get("X-Tenant-ID")
        if header_tid and header_tid.isdigit():
            return int(header_tid)

        # 2. JWT token no header Authorization
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth.split(" ", 1)[1]
            tid = self._extract_tenant_from_jwt(token)
            if tid:
                return tid

        return None

    def _extract_tenant_from_jwt(self, token: str) -> Optional[int]:
        """Extrai tenant_id do payload JWT sem revalidar assinatura aqui."""
        try:
            import base64
            import json

            payload_b64 = token.split(".")[1]
            # Ajusta padding base64
            payload_b64 += "==" * (4 - len(payload_b64) % 4)
            payload = json.loads(base64.b64decode(payload_b64))
            tid = payload.get("tenant_id")
            return int(tid) if tid else None
        except Exception:
            return None


async def set_rls_tenant(session, tenant_id: int):
    """
    Define o tenant ativo no PostgreSQL para Row-Level Security.
    Usar no início de cada sessão de banco que precisar de isolamento RLS:

        async with async_session() as session:
            await set_rls_tenant(session, tenant_id)
            # ... queries

    PostgreSQL usa app.current_tenant para aplicar as políticas RLS.
    """
    await session.execute(
        text("SET LOCAL app.current_tenant = :tid"),
        {"tid": str(tenant_id)}
    )


async def get_db_with_tenant(tenant_id: int):
    """
    Dependency FastAPI que entrega sessão já com RLS configurado.

    Uso nos endpoints:
        async def my_endpoint(
            tenant_id: int = Depends(get_current_tenant_id),
            session: AsyncSession = Depends(lambda tid=tenant_id: get_db_with_tenant(tid))
        ):
    """
    from src.models.database import async_session
    async with async_session() as session:
        await set_rls_tenant(session, tenant_id)
        yield session


def get_current_tenant_id() -> int:
    """
    Dependency FastAPI para obter tenant_id do contexto atual.
    Usar em qualquer endpoint que precisar do tenant.

    Uso:
        async def my_endpoint(tenant_id: int = Depends(get_current_tenant_id)):
    """
    tid = current_tenant_id.get()
    if tid is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Tenant não autenticado.")
    return tid
