import time
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request


class PerformanceMiddleware(BaseHTTPMiddleware):
    """Adiciona header X-Process-Time com o tempo de resposta em segundos."""

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start
        response.headers["X-Process-Time"] = f"{duration:.4f}"
        return response
