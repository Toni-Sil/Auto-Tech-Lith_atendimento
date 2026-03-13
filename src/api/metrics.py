"""
Rota de métricas Prometheus.

GET /api/v1/metrics
  - Requer header: Authorization: Bearer {METRICS_TOKEN}
  - Retorna: texto no formato Prometheus exposition format

Configuração no .env:
  METRICS_TOKEN=seu-token-secreto
"""

import logging
import os

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

logger = logging.getLogger(__name__)

metrics_router = APIRouter()


def _get_metrics_token() -> str:
    token = os.getenv("METRICS_TOKEN", "")
    if not token:
        logger.warning(
            "⚠️ METRICS_TOKEN não definido. Endpoint /metrics está exposto sem autenticação!"
        )
    return token


@metrics_router.get(
    "/metrics",
    include_in_schema=False,  # Não aparece no Swagger público
    response_class=PlainTextResponse,
    summary="Prometheus Metrics",
    description="Expõe métricas de performance no formato Prometheus. Requer Bearer token.",
)
async def prometheus_metrics(request: Request) -> PlainTextResponse:
    """
    Endpoint de métricas para scraping pelo Prometheus ou Dokploy.

    Autenticação via Bearer token (METRICS_TOKEN no .env).
    Configure no Prometheus:
      - targets: ['seu-dominio.com']
        params:
          path: ['/api/v1/metrics']
        bearer_token: 'seu_token'
    """
    expected_token = _get_metrics_token()

    if expected_token:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization header ausente. Use: Authorization: Bearer {METRICS_TOKEN}",
                headers={"WWW-Authenticate": "Bearer"},
            )
        provided_token = auth_header[len("Bearer ") :]
        if provided_token != expected_token:
            logger.warning(
                f"⚠️ Tentativa de acesso não autorizado ao /metrics de {request.client.host if request.client else 'unknown'}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Token de métricas inválido.",
            )

    metrics_data = generate_latest()
    return PlainTextResponse(
        content=metrics_data.decode("utf-8"),
        media_type=CONTENT_TYPE_LATEST,
    )
