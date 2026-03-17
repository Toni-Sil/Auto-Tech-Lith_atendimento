import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

SLOW_REQUEST_THRESHOLD_MS = 500


class PerformanceMiddleware(BaseHTTPMiddleware):
    """Adds Server-Timing header and logs slow requests (>500ms)."""

    async def dispatch(self, request: Request, call_next) -> Response:
        t0 = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

        response.headers["Server-Timing"] = f"total;dur={elapsed_ms}"

        if elapsed_ms > SLOW_REQUEST_THRESHOLD_MS:
            logger.warning(
                f"SLOW REQUEST {elapsed_ms}ms | {request.method} {request.url.path}"
            )

        return response
