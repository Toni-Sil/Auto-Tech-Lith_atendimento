"""
Middleware global de Rate Limiting por IP.

Aplicado em todas as rotas automaticamente, com limites diferentes
por categoria (auth, webhooks, api, default).

IPs na whitelist (configurável via RATE_LIMIT_WHITELIST no .env) são isentos.
Rotas de painel interno (master, admin, client) são isentas por padrão.
JWT com role master_admin é isento de rate limiting.
"""

import logging
import os
import time

from fastapi import Request, Response
from starlette.middleware.base import (BaseHTTPMiddleware,
                                       RequestResponseEndpoint)
from starlette.responses import JSONResponse

from src.utils.rate_limit import (RATE_LIMIT_RULES, _check_rate_limit_redis,
                                  _get_client_ip, _get_redis,
                                  _get_route_category)

logger = logging.getLogger(__name__)

# ── Rotas completamente isentas do rate limiting ───────────────────────────────
EXEMPT_PREFIXES = (
    "/health",
    "/static",
    "/favicon.ico",
    "/api/v1/metrics",    # protegido por token separado
    "/master",            # painel master admin interno
    "/master.html",
    "/admin",             # dashboard admin interno
    "/client",            # portal do cliente
    "/client.html",
    "/onboarding",        # fluxo de onboarding público
    "/css",               # static assets
    "/js",
    "/assets",
    "/img",
)


# ── IPs sempre isentos ──────────────────────────────────────────────────────────────
def _get_whitelist() -> set[str]:
    """Loopback + IPs configurados via env RATE_LIMIT_WHITELIST (separados por vírgula)."""
    base = {"127.0.0.1", "::1"}
    env_whitelist = os.getenv("RATE_LIMIT_WHITELIST", "")
    if env_whitelist:
        for entry in env_whitelist.split(","):
            base.add(entry.strip())
    return base


# ── Verifica se JWT é master_admin (sem validar assinatura — só isenta do rate limit) ──
def _is_master_token(request: Request) -> bool:
    """
    Lê o JWT do header Authorization e verifica se o claim 'role' é 'master_admin'.
    Não valida a assinatura — apenas decodifica o payload para isentar do rate limit.
    Autenticação real é feita pelos endpoints.
    """
    try:
        import base64
        import json

        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return False
        token = auth[7:]
        parts = token.split(".")
        if len(parts) != 3:
            return False
        # Decodifica o payload (parte do meio) sem verificar assinatura
        payload_b64 = parts[1]
        # Adiciona padding se necessário
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload = json.loads(base64.b64decode(payload_b64).decode("utf-8"))
        role = payload.get("role", "")
        return role in ("master_admin", "superadmin", "system")
    except Exception:
        return False


# ── Middleware ───────────────────────────────────────────────────────────────────
class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware global de rate limiting aplicado em todas as requisições."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path

        # 1. Pular rotas isentas
        if any(path.startswith(p) for p in EXEMPT_PREFIXES):
            return await call_next(request)

        # 2. Pular loopback + whitelist de IPs
        ip = _get_client_ip(request)
        if ip in _get_whitelist():
            return await call_next(request)

        # 3. Pular tokens master_admin (sem risco de bloquear o dono do sistema)
        if _is_master_token(request):
            logger.debug("[RateLimit] Isento: token master_admin para %s", path)
            return await call_next(request)

        # 4. Redis indisponível — fail-open
        redis_client = _get_redis()
        if redis_client is None:
            return await call_next(request)

        category = _get_route_category(path)
        limit, window = RATE_LIMIT_RULES.get(category, RATE_LIMIT_RULES["default"])
        key = f"rl:{ip}:{category}"

        try:
            is_allowed, current_count, reset_ts = _check_rate_limit_redis(
                redis_client, key, limit, window
            )
        except Exception as e:
            logger.warning(f"⚠️ RateLimitMiddleware: erro Redis ({e}). Ignorando.")
            return await call_next(request)

        rl_headers = {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(max(0, limit - current_count - 1)),
            "X-RateLimit-Reset": str(reset_ts),
            "X-RateLimit-Category": category,
        }

        if not is_allowed:
            retry_after = max(1, reset_ts - int(time.time()))
            logger.warning(
                "[RateLimit] 429 bloqueado: ip=%s path=%s category=%s count=%d limit=%d",
                ip, path, category, current_count, limit
            )
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too Many Requests",
                    "message": f"Limite de {limit} requisições por {window}s excedido. Aguarde {retry_after}s.",
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    **rl_headers,
                },
            )

        response = await call_next(request)
        for k, v in rl_headers.items():
            response.headers[k] = v
        return response
