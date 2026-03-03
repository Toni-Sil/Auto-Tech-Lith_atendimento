"""
Middleware de Métricas de Performance via Prometheus.

Coleta as seguintes métricas para cada requisição HTTP:
  - http_requests_total          : counter por método, rota normalizada e status
  - http_request_duration_seconds: histograma de latência por rota
  - http_requests_in_flight      : gauge de requisições simultâneas
  - http_errors_total            : counter de erros 5xx por rota

As métricas são expostas via rota /api/v1/metrics.
"""

import time
import logging

from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
)
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.routing import Match

logger = logging.getLogger(__name__)

# ── Definição das métricas Prometheus ─────────────────────────────────────────

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total de requisições HTTP por método, rota e status",
    ["method", "route", "status_code"],
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "Latência das requisições HTTP em segundos",
    ["method", "route"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

REQUESTS_IN_FLIGHT = Gauge(
    "http_requests_in_flight",
    "Número de requisições sendo processadas simultaneamente",
)

ERROR_COUNT = Counter(
    "http_errors_total",
    "Total de erros HTTP 5xx por rota",
    ["method", "route", "status_code"],
)

RATE_LIMITED_COUNT = Counter(
    "http_rate_limited_total",
    "Total de requisições bloqueadas pelo rate limiter (HTTP 429)",
    ["category"],
)


def _normalize_route(request: Request) -> str:
    """
    Retorna o template da rota (ex: '/api/v1/tenant/{tenant_id}')
    em vez do path concreto, para não criar cardinalidade infinita nas métricas.
    """
    try:
        for route in request.app.routes:
            match, _ = route.matches(request.scope)
            if match == Match.FULL:
                path = getattr(route, "path", None)
                if path and isinstance(path, str):
                    return path
    except Exception:
        pass
    # Fallback: truncar path concreto para evitar explosão de cardinalidade
    parts = request.url.path.split("/")
    # Mantém apenas os 4 primeiros segmentos: /api/v1/<module>/<action>
    return "/" + "/".join(parts[1:5]) if len(parts) > 5 else request.url.path


class PrometheusMetricsMiddleware(BaseHTTPMiddleware):
    """Middleware que coleta métricas de performance para todas as requisições."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Pular o próprio endpoint de métricas (evitar auto-coleta)
        if request.url.path == "/api/v1/metrics":
            return await call_next(request)

        route = _normalize_route(request)
        method = request.method

        REQUESTS_IN_FLIGHT.inc()
        start_time = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception as exc:
            # Erro não tratado (500) — dec() é feito no finally
            duration = time.perf_counter() - start_time
            REQUEST_LATENCY.labels(method=method, route=route).observe(duration)
            REQUEST_COUNT.labels(method=method, route=route, status_code="500").inc()
            ERROR_COUNT.labels(method=method, route=route, status_code="500").inc()
            raise exc
        finally:
            # Decrementar sempre, seja sucesso ou exceção
            REQUESTS_IN_FLIGHT.dec()

        duration = time.perf_counter() - start_time
        status_code = str(response.status_code)

        REQUEST_LATENCY.labels(method=method, route=route).observe(duration)
        REQUEST_COUNT.labels(method=method, route=route, status_code=status_code).inc()

        if response.status_code >= 500:
            ERROR_COUNT.labels(method=method, route=route, status_code=status_code).inc()

        if response.status_code == 429:
            category = response.headers.get("X-RateLimit-Category", "unknown")
            RATE_LIMITED_COUNT.labels(category=category).inc()

        return response
