import sys
import os
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from src.config import settings
from src.middleware.metrics import PrometheusMetricsMiddleware
from src.middleware.rate_limit_middleware import RateLimitMiddleware

# -------------------------------------------------------------------------
# CRITICAL FIX: Force UTF-8 encoding for Windows Console to prevent crashes
# when logging emojis or special characters.
# -------------------------------------------------------------------------
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except Exception:
            pass

# Configuração de Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# ── Ordem dos middlewares (aplicados de baixo para cima por Starlette) ────────
# 1. Métricas: captura latência e status de TODAS as requisições
app.add_middleware(PrometheusMetricsMiddleware)
# 2. Rate Limit global: bloqueia IPs abusivos antes de processar rotas
app.add_middleware(RateLimitMiddleware)

# Disable caching for frontend/static files — only active in DEBUG/development mode
if getattr(settings, "APP_DEBUG", False):
    @app.middleware("http")
    async def add_no_cache_header(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.endswith(".html") or request.url.path.endswith(".js") or request.url.path.endswith(".css"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

# Configuração de CORS
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Configuração de Middleware de Segurança
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com;"
    return response

# Montar arquivos estáticos do frontend (Dashboard) será feito no final

@app.get("/health")
async def health_check():
    return {"status": "ok", "project": settings.PROJECT_NAME, "version": settings.VERSION}

# Importar rotas da API
from src.api.routes import api_router
from src.api.auth import auth_router
from src.api.tenant import tenant_router
from src.api.roles import role_router
from src.api.mfa import mfa_router
from src.api.preferences import pref_router
from src.api.locales import locale_router
from src.api.automations import automation_router
from src.api.notifications import notification_router
from src.api.apikeys import apikey_router
from src.api.reports import report_router
# New SaaS architecture routers
from src.api.ai_config import ai_config_router
from src.api.usage import usage_router, billing_router
from src.api.workflow import workflow_router
from src.api.master_admin import master_router
from src.api.leads import leads_router
from src.api.tenant_quota import quota_router
from src.api.webhooks import webhooks_router
from src.api.butler import butler_router

from src.api.metrics import metrics_router

app.include_router(auth_router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
app.include_router(mfa_router, prefix=f"{settings.API_V1_STR}/auth/mfa", tags=["mfa"])
app.include_router(tenant_router, prefix=f"{settings.API_V1_STR}/tenant", tags=["tenant"])
app.include_router(role_router, prefix=f"{settings.API_V1_STR}/roles", tags=["roles"])
app.include_router(pref_router, prefix=f"{settings.API_V1_STR}/preferences", tags=["preferences"])
app.include_router(locale_router, prefix=f"{settings.API_V1_STR}/locales", tags=["locales"])
app.include_router(automation_router, prefix=f"{settings.API_V1_STR}/automations", tags=["automations"])
app.include_router(notification_router, prefix=f"{settings.API_V1_STR}/notifications", tags=["notifications"])
app.include_router(apikey_router, prefix=f"{settings.API_V1_STR}/apikeys", tags=["apikeys"])
app.include_router(report_router, prefix=f"{settings.API_V1_STR}/reports", tags=["reports"])
# New SaaS architecture routers
app.include_router(ai_config_router, prefix=f"{settings.API_V1_STR}/ai-config", tags=["ai-config"])
app.include_router(usage_router, prefix=f"{settings.API_V1_STR}/usage", tags=["usage"])
app.include_router(billing_router, prefix=f"{settings.API_V1_STR}/billing", tags=["billing"])
app.include_router(workflow_router, prefix=f"{settings.API_V1_STR}/workflow", tags=["workflow"])
app.include_router(master_router, prefix=f"{settings.API_V1_STR}/master", tags=["master-admin"])
app.include_router(leads_router,  prefix=f"{settings.API_V1_STR}/master", tags=["master-leads"])
app.include_router(quota_router,  prefix=f"{settings.API_V1_STR}/master", tags=["master-quotas"])
app.include_router(butler_router,  prefix=f"{settings.API_V1_STR}/master", tags=["butler-agent"])
app.include_router(webhooks_router, prefix=f"{settings.API_V1_STR}/webhooks", tags=["webhooks"])
app.include_router(metrics_router, prefix=f"{settings.API_V1_STR}", tags=["observability"])
app.include_router(api_router, prefix=settings.API_V1_STR)

# Montar arquivos estáticos do frontend (Dashboard) por último
import os
frontend_path = os.path.join(os.getcwd(), "frontend")

if os.path.exists(frontend_path):
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")
    
    # Serve favicon explicitly (or just let the catch-all below handle it if it exists)
    from fastapi.responses import FileResponse
    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        favicon_path = os.path.join(frontend_path, "favicon.ico")
        if os.path.exists(favicon_path):
            return FileResponse(favicon_path)
        return FileResponse(os.path.join(frontend_path, "index.html")) # Fallback or just 404 cleanly

    # Mount root to serve index.html for SPA-like behavior or just static files
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")
else:
    logger.warning(f"Frontend directory not found at {frontend_path}")

@app.on_event("startup")
async def startup_event():
    import os
    # Check ENCRYPTION_KEY — required for AI Config key vault
    if not settings.ENCRYPTION_KEY:
        if settings.ENV == "production":
            logger.error(
                "🚨 CRITICAL: ENCRYPTION_KEY is not set in production! "
                "AI Config key vault will NOT function. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        else:
            logger.warning(
                "⚠️  ENCRYPTION_KEY env variable is not set. "
                "AI Config key vault will not function. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
    else:
        logger.info("✅ ENCRYPTION_KEY is set. AI Config key vault active.")
    # Start Telegram Bot Worker in background
    import asyncio
    from src.workers.telegram_bot import telegram_bot_worker
    asyncio.create_task(telegram_bot_worker())
    logger.info("Startup: Telegram Worker launched.")
    # Start Butler Agent APScheduler
    from src.workers.butler_worker import create_butler_scheduler
    butler_scheduler = create_butler_scheduler()
    butler_scheduler.start()
    logger.info("Startup: Butler Agent scheduler started with 5 background jobs.")
    logger.info("Startup: SaaS multi-tenant architecture routes active.")

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
