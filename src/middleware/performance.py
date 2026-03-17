"""Performance middleware — Server-Timing header + request duration logging."""
import time
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)


class PerformanceMiddleware(BaseHTTPMiddleware):
    """Adds Server-Timing header and logs slow requests (>500ms)."""

    SLOW_REQUEST_THRESHOLD_MS = 500

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        response.headers["Server-Timing"] = f'total;dur={duration_ms:.1f}'
        response.headers["X-Response-Time"] = f"{duration_ms:.1f}ms"

        if duration_ms > self.SLOW_REQUEST_THRESHOLD_MS:
            logger.warning(
                f"🐢 Slow request: {request.method} {request.url.path} "
                f"took {duration_ms:.0f}ms"
            )

        return response
