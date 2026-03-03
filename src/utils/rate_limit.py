"""
Rate Limiter via Redis — Sliding Window Algorithm.

Suporta múltiplos workers (produção no Dokploy) pois o estado
é centralizado no Redis, não em memória local.

Limites por tipo de rota:
  - "auth"     : 5 requisições por 60 segundos (login, recovery)
  - "api"      : 120 requisições por 60 segundos (rotas protegidas gerais)
  - "webhooks" : 300 requisições por 60 segundos (alta frequência de eventos)
  - "default"  : 60 requisições por 60 segundos

Se o Redis não estiver disponível, o limitador falha **aberto** (não bloqueia),
garantindo disponibilidade em caso de falha transitória do Redis.
"""

from __future__ import annotations

import time
import logging
from typing import Optional

from fastapi import Request, HTTPException, status

logger = logging.getLogger(__name__)

# ── Limites por categoria de rota ─────────────────────────────────────────────
RATE_LIMIT_RULES: dict[str, tuple[int, int]] = {
    "auth":     (5, 60),    # 5 req / 60s  — rotas de autenticação
    "webhooks": (300, 60),  # 300 req / 60s — eventos de webhook
    "api":      (120, 60),  # 120 req / 60s — API geral autenticada
    "default":  (60, 60),   # 60 req / 60s  — demais rotas
}


def _get_route_category(path: str) -> str:
    """Determina a categoria de rate limit com base no prefixo da rota."""
    if "/auth" in path:
        return "auth"
    if "/webhooks" in path:
        return "webhooks"
    if path.startswith("/api/"):
        return "api"
    return "default"


# ── Cliente Redis (lazy-loaded, singleton) ────────────────────────────────────
_redis_client = None


def _get_redis() -> Optional[object]:
    """Retorna o cliente Redis, criando-o se necessário. Retorna None se indisponível."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        import redis
        import os
        redis_password = os.getenv("REDIS_PASSWORD", "redis2026")
        # No docker-compose, o Redis está acessível via hostname 'redis'
        redis_host = os.getenv("REDIS_HOST", "redis")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))
        client = redis.Redis(
            host=redis_host,
            port=redis_port,
            password=redis_password,
            db=7,  # DB separado para rate limiting (não conflita com Evolution API no DB 6)
            decode_responses=True,
            socket_timeout=1,
            socket_connect_timeout=1,
        )
        client.ping()
        _redis_client = client
        logger.info("✅ Rate Limiter: Redis conectado com sucesso.")
        return _redis_client
    except Exception as e:
        logger.warning(f"⚠️ Rate Limiter: Redis indisponível ({e}). Operando sem limitação.")
        return None


# ── Sliding Window Rate Limiter ────────────────────────────────────────────────

def _check_rate_limit_redis(redis_client, key: str, limit: int, window: int) -> tuple[bool, int, int]:
    """
    Implementa o algoritmo Sliding Window via Redis Sorted Set.

    Retorna: (is_allowed, current_count, reset_ts)
    """
    now = time.time()
    window_start = now - window

    pipe = redis_client.pipeline()
    # Remove entradas fora da janela
    pipe.zremrangebyscore(key, 0, window_start)
    # Conta entradas na janela
    pipe.zcard(key)
    # Adiciona a requisição atual com score = timestamp
    pipe.zadd(key, {str(now): now})
    # Define TTL para limpeza automática
    pipe.expire(key, window + 1)
    results = pipe.execute()

    current_count = results[1]  # count antes de adicionar a atual
    is_allowed = current_count < limit
    reset_ts = int(now + window)
    return is_allowed, current_count, reset_ts


async def rate_limit_check(
    request: Request,
    limit: int = 5,
    window_seconds: int = 60,
    category: Optional[str] = None,
) -> None:
    """
    Verifica o rate limit para a requisição atual.

    Compatível com a assinatura atual usada em auth.py — drop-in replacement.
    Se o Redis não estiver disponível, falha aberta (não bloqueia).
    """
    redis_client = _get_redis()
    if redis_client is None:
        return  # fail-open: Redis indisponível, não bloqueia

    ip = _get_client_ip(request)
    route = request.url.path

    # Usa categoria explícita ou detecta automaticamente
    cat = category or _get_route_category(route)
    auto_limit, auto_window = RATE_LIMIT_RULES.get(cat, RATE_LIMIT_RULES["default"])

    # Argumentos explícitos (limit, window_seconds) sobrescrevem os automáticos
    # apenas se forem diferentes dos defaults, preservando compatibilidade legada
    effective_limit = limit if limit != 5 else auto_limit
    effective_window = window_seconds if window_seconds != 60 else auto_window

    key = f"rl:{ip}:{cat}"

    try:
        is_allowed, current_count, reset_ts = _check_rate_limit_redis(
            redis_client, key, effective_limit, effective_window
        )
    except Exception as e:
        logger.warning(f"⚠️ Rate Limiter: erro ao verificar Redis ({e}). Ignorando.")
        return  # fail-open

    # Adicionar headers RateLimit à resposta (via request.state para uso no middleware)
    request.state.rate_limit_headers = {
        "X-RateLimit-Limit": str(effective_limit),
        "X-RateLimit-Remaining": str(max(0, effective_limit - current_count - 1)),
        "X-RateLimit-Reset": str(reset_ts),
        "X-RateLimit-Category": cat,
    }

    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "Too many requests",
                "message": f"Limite de {effective_limit} requisições por {effective_window}s excedido. Tente novamente após {reset_ts}.",
                "retry_after": effective_window,
            },
            headers={
                "Retry-After": str(effective_window),
                "X-RateLimit-Limit": str(effective_limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(reset_ts),
            },
        )


def _get_client_ip(request: Request) -> str:
    """
    Extrai o IP real do cliente, respeitando proxies reversos.
    Suporta os headers: X-Forwarded-For, X-Real-IP, CF-Connecting-IP (Cloudflare).
    """
    # Cloudflare
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()
    # Nginx / Traefik proxy reverso
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    # X-Real-IP
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    # Fallback
    return request.client.host if request.client else "unknown"


class RateLimiter:
    """
    Classe auxiliar para criar dependências FastAPI com limites customizados.

    Uso:
        @router.post("/endpoint")
        async def my_endpoint(
            request: Request,
            _: None = Depends(RateLimiter(limit=10, window_seconds=30))
        ):
            ...
    """
    def __init__(self, limit: int, window_seconds: int = 60, category: str = "api"):
        self.limit = limit
        self.window_seconds = window_seconds
        self.category = category

    async def __call__(self, request: Request) -> None:
        await rate_limit_check(
            request,
            limit=self.limit,
            window_seconds=self.window_seconds,
            category=self.category,
        )
