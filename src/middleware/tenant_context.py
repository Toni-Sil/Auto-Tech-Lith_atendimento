"""
Tenant Context Middleware

Injects tenant_id into every request automatically:
  - From JWT sub-claim (authenticated routes)
  - From X-Tenant-ID header (API key routes)
  - From subdomain (future: subdomain routing)

All downstream services read from request.state.tenant_id.
Prevents cross-tenant data leaks.
"""

from typing import Optional

from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from jose import jwt, JWTError

from src.utils.logger import setup_logger

logger = setup_logger(__name__)

# Routes that are tenant-agnostic (public/system)
PUBLIC_PATHS = {
    "/health",
    "/",
    "/login",
    "/login.html",
    "/favicon.ico",
    "/api/v1/auth/token",
    "/api/v1/auth/register",
    "/api/v1/webhooks/whatsapp",
    "/api/v1/webhooks/telegram",
    "/api/v1/master",
    "/docs",
    "/openapi.json",
    "/metrics",
}


def _is_public(path: str) -> bool:
    """Check if the path is tenant-agnostic."""
    for pub in PUBLIC_PATHS:
        if path == pub or path.startswith(pub):
            return True
    # Static assets
    if any(path.endswith(ext) for ext in (".js", ".css", ".html", ".png", ".ico", ".svg")):
        return True
    return False


def _extract_tenant_from_jwt(token: str) -> Optional[int]:
    """Decode JWT and extract tenant_id without full validation (middleware perf)."""
    try:
        # Decode without verifying signature here — full verification done in auth deps
        payload = jwt.get_unverified_claims(token)
        tid = payload.get("tenant_id")
        return int(tid) if tid is not None else None
    except (JWTError, Exception):
        return None


class TenantContextMiddleware(BaseHTTPMiddleware):
    """
    Extracts and attaches tenant_id to request.state for every request.

    Priority order:
      1. JWT Bearer token (Authorization header)
      2. X-Tenant-ID header (webhook / API key calls)
      3. None (public routes allowed, protected routes blocked by auth deps)
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Initialize state
        request.state.tenant_id = None
        request.state.tenant_resolved = False

        # 1. Try JWT
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            tid = _extract_tenant_from_jwt(token)
            if tid:
                request.state.tenant_id = tid
                request.state.tenant_resolved = True
                logger.debug(f"[TenantCtx] tenant_id={tid} from JWT | {path}")

        # 2. Try X-Tenant-ID header (fallback for API keys / webhooks)
        if not request.state.tenant_resolved:
            raw_tid = request.headers.get("X-Tenant-ID")
            if raw_tid:
                try:
                    request.state.tenant_id = int(raw_tid)
                    request.state.tenant_resolved = True
                    logger.debug(f"[TenantCtx] tenant_id={raw_tid} from header | {path}")
                except ValueError:
                    pass

        response = await call_next(request)
        return response


# ── Dependency helper ─────────────────────────────────────────────────────────

def get_current_tenant_id(request: Request) -> int:
    """
    FastAPI dependency — returns tenant_id or raises 401.
    Use in any route that requires tenant isolation.

    Usage:
        @router.get("/tickets")
        async def list_tickets(tenant_id: int = Depends(get_current_tenant_id)):
            ...
    """
    tid = getattr(request.state, "tenant_id", None)
    if tid is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant context not established. Authenticate first.",
        )
    return tid


def get_optional_tenant_id(request: Request) -> Optional[int]:
    """Like get_current_tenant_id but returns None instead of raising (for public routes)."""
    return getattr(request.state, "tenant_id", None)
