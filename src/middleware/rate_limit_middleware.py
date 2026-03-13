"""
Middleware global de Rate Limiting por IP.

Aplicado em todas as rotas automaticamente, com limites diferentes
por categoria (auth, webhooks, api, default).

IPs na whitelist (configurável via RATE_LIMIT_WHITELIST no .env) são isentos.
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

# Rotas excluídas do rate limiting global (health, metrics, static files)
EXEMPT_PREFIXES = (
    "/health",
    "/static",
    "/favicon.ico",
    "/api/v1/metrics",  # protegido por token separado
)


# IPs sempre isentos (loopback + configurável via env)
def _get_whitelist() -> set[str]:
    base = {"127.0.0.1", "::1"}
    env_whitelist = os.getenv("RATE_LIMIT_WHITELIST", "")
    if env_whitelist:
        for entry in env_whitelist.split(","):
            base.add(entry.strip())
    return base


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware global de rate limiting aplicado em todas as requisições."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path

        # Pular rotas isentas
        if any(path.startswith(p) for p in EXEMPT_PREFIXES):
            return await call_next(request)

        ip = _get_client_ip(request)

        # Pular IPs na whitelist
        if ip in _get_whitelist():
            return await call_next(request)

        redis_client = _get_redis()
        if redis_client is None:
            # fail-open: Redis indisponível
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

        # Headers informativos
        rl_headers = {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(max(0, limit - current_count - 1)),
            "X-RateLimit-Reset": str(reset_ts),
            "X-RateLimit-Category": category,
        }

        if not is_allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too Many Requests",
                    "message": f"Limite de {limit} requisições por {window}s excedido para IP {ip}.",
                    "retry_after": window,
                },
                headers={
                    "Retry-After": str(window),
                    **rl_headers,
                },
            )

        # Requisição permitida — processar e adicionar headers à resposta
        response = await call_next(request)
        for k, v in rl_headers.items():
            response.headers[k] = v

        return response
