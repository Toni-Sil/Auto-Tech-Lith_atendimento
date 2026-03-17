import logging
import os
import secrets
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from src.config import settings
from src.middleware.metrics import PrometheusMetricsMiddleware
from src.middleware.performance import PerformanceMiddleware
from src.middleware.rate_limit_middleware import RateLimitMiddleware
from src.middleware.tenant_context import TenantContextMiddleware  # Sprint 1
from src.middleware.request_id import RequestIDMiddleware

# ── UTF-8 for Windows console ─────────────────────────────────────────────
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── STARTUP ───────────────────────────────────────────────────────────
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    import src.models.admin
    import src.models.agent_profile
    import src.models.api_key
    import src.models.audit
    import src.models.automation
    import src.models.base_tenant
    import src.models.butler_log
    import src.models.config_model
    import src.models.conversation
    import src.models.customer
    import src.models.lead
    import src.models.lead_interaction
    import src.models.meeting
    import src.models.notification
    import src.models.preferences
    import src.models.product
    import src.models.recovery
    import src.models.role
    import src.models.sales_workflow
    import src.models.subscription
    import src.models.tenant
    import src.models.tenant_ai_config
    import src.models.tenant_quota
    import src.models.ticket
    import src.models.usage_log
    import src.models.user_session
    import src.models.vault
    import src.models.webhook_config
    import src.models.whatsapp
    from src.models.database import Base

    # ── Alembic / create_all fallback ─────────────────────────────────────
    alembic_cfg_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "alembic.ini"
    )
    if os.path.exists(alembic_cfg_path):
        try:
            import asyncio
            from alembic import command as alembic_command
            from alembic.config import Config as AlembicConfig
            from functools import partial

            alembic_cfg = AlembicConfig(alembic_cfg_path)
            alembic_cfg.set_main_option(
                "sqlalchemy.url",
                settings.DATABASE_URL.replace("+asyncpg", "+psycopg2"),
            )
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, partial(alembic_command.upgrade, alembic_cfg, "head")
            )
            logger.info("✅ Alembic: migrations applied up to head.")
        except Exception as e:
            logger.error(f"❌ Alembic migration failed: {e}")
            raise
    else:
        logger.warning("⚠️ alembic.ini not found — falling back to create_all (dev only).")
        engine = create_async_engine(settings.DATABASE_URL)
        async with engine.begin() as conn:
            logger.info("Database: Checking/creating tables...")
            await conn.run_sync(Base.metadata.create_all)

            from sqlalchemy import inspect
            from sqlalchemy import text as sa_text

            def _run_migrations(connection):
                inspector = inspect(connection)
                try:
                    existing = [
                        col["name"] for col in inspector.get_columns("evolution_instances")
                    ]
                except Exception:
                    existing = []
                migrations_to_run = []
                if "evolution_ip" not in existing:
                    migrations_to_run.append(
                        "ALTER TABLE evolution_instances ADD COLUMN IF NOT EXISTS evolution_ip VARCHAR"
                    )
                if "owner_email" not in existing:
                    migrations_to_run.append(
                        "ALTER TABLE evolution_instances ADD COLUMN IF NOT EXISTS owner_email VARCHAR"
                    )
                for sql in migrations_to_run:
                    connection.execute(sa_text(sql))
                    logger.info(f"Migration applied: {sql}")

            try:
                await conn.run_sync(_run_migrations)
            except Exception as e:
                logger.warning(f"Auto-migration warning: {e}")
        await engine.dispose()
        logger.info("Database: Initialization complete.")

    if not settings.ENCRYPTION_KEY:
        if settings.ENV == "production":
            logger.error(
                "🚨 CRITICAL: ENCRYPTION_KEY is not set in production! "
                'Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
            )
        else:
            logger.warning("⚠️  ENCRYPTION_KEY env variable is not set.")
    else:
        logger.info("✅ ENCRYPTION_KEY is set.")

    if settings.TELEGRAM_BOT_TOKEN and settings.PUBLIC_URL:
        from src.services.telegram_service import telegram_service

        webhook_url = f"{settings.PUBLIC_URL.rstrip('/')}{settings.API_V1_STR}/webhooks/telegram"
        success = await telegram_service.set_webhook(webhook_url)
        if success:
            logger.info(f"Startup: Telegram Webhook set to {webhook_url}")
        else:
            logger.error("Startup: Failed to set Telegram Webhook")
    else:
        logger.warning("Startup: Telegram Webhook not configured.")

    from src.workers.butler_worker import create_butler_scheduler

    butler_scheduler = create_butler_scheduler()
    butler_scheduler.start()
    logger.info("✅ Butler Agent scheduler started.")
    logger.info("✅ Middlewares: RequestID → Performance → Tenant → Prometheus → RateLimit")

    try:
        from src.scripts.create_master_admin import ensure_master_admin

        _seed_engine = create_async_engine(settings.DATABASE_URL, echo=False)
        _SeedSession = sessionmaker(_seed_engine, class_=AsyncSession, expire_on_commit=False)
        async with _SeedSession() as _seed_session:
            await ensure_master_admin(_seed_session, reset_password=False)
        await _seed_engine.dispose()
        logger.info("✅ Master admin verificado/criado.")
    except Exception as _e:
        logger.warning(f"⚠️ Auto-seed master admin falhou: {_e}")

    yield  # ── app running ──────────────────────────────────────────────

    # ── SHUTDOWN ──────────────────────────────────────────────────────────
    try:
        from src.agents.customer_service_agent import _redis_pool

        if _redis_pool is not None:
            await _redis_pool.aclose()
            logger.info("✅ Redis async pool fechado.")
    except Exception as e:
        logger.warning(f"⚠️ Erro ao fechar Redis pool: {e}")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

# ── Middleware stack (Starlette: applied bottom-up = last-added runs first) ──
# Execution order on REQUEST:  RequestID → Performance → Tenant → Prometheus → RateLimit → handler
# Execution order on RESPONSE: handler → RateLimit → Prometheus → Tenant → Performance → RequestID
app.add_middleware(RateLimitMiddleware)          # innermost
app.add_middleware(PrometheusMetricsMiddleware)
app.add_middleware(TenantContextMiddleware)
app.add_middleware(PerformanceMiddleware)
app.add_middleware(RequestIDMiddleware)          # outermost

if getattr(settings, "APP_DEBUG", False):
    @app.middleware("http")
    async def add_no_cache_header(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.endswith((".html", ".js", ".css")):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

if settings.BACKEND_CORS_ORIGINS:
    origins = list(settings.BACKEND_CORS_ORIGINS)
    if settings.PUBLIC_URL and settings.PUBLIC_URL.rstrip("/") not in origins:
        origins.append(settings.PUBLIC_URL.rstrip("/"))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# ── CSP nonce injection ────────────────────────────────────────────────────
def _inject_csp_nonce(html_content: str, nonce: str) -> str:
    import re
    html_content = re.sub(
        r"<script(?![^>]*nonce)([^>]*)>",
        lambda m: f'<script nonce="{nonce}"{m.group(1)}>',
        html_content,
    )
    html_content = re.sub(
        r"<style(?![^>]*nonce)([^>]*)>",
        lambda m: f'<style nonce="{nonce}"{m.group(1)}>',
        html_content,
    )
    return html_content


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    nonce = secrets.token_urlsafe(16)
    request.state.csp_nonce = nonce

    response = await call_next(request)

    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"

    connect_origins = ["'self'", "http://localhost:8000", "http://127.0.0.1:8000"]
    if settings.PUBLIC_URL:
        public_domain = settings.PUBLIC_URL.split("://")[-1].split("/")[0]
        connect_origins += [f"https://{public_domain}", f"wss://{public_domain}"]

    # Tailwind é compilado localmente — CDN não é necessário
    csp = (
        f"default-src 'self'; "
        f"script-src 'self' 'nonce-{nonce}' https://cdn.jsdelivr.net; "
        f"style-src 'self' 'nonce-{nonce}' 'unsafe-inline' https://fonts.googleapis.com; "
        f"font-src 'self' https://fonts.gstatic.com data:; "
        f"img-src 'self' data: blob:; "
        f"connect-src {' '.join(connect_origins)};"
    )
    response.headers["Content-Security-Policy"] = csp

    content_type = response.headers.get("content-type", "")
    if "text/html" in content_type and hasattr(response, "body"):
        try:
            body = response.body.decode("utf-8")
            body = _inject_csp_nonce(body, nonce)
            return HTMLResponse(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
            )
        except Exception:
            pass

    return response


# ── Health check (com dependências) ───────────────────────────────────────
@app.get("/health", tags=["observability"])
async def health_check():
    """Returns status of app + DB + Redis + Evolution API."""
    import time

    result: dict = {
        "status": "ok",
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "env": settings.ENV,
        "dependencies": {},
    }
    overall_ok = True

    # PostgreSQL
    if "sqlite" not in settings.DATABASE_URL:
        try:
            t0 = time.perf_counter()
            from sqlalchemy.ext.asyncio import create_async_engine
            from sqlalchemy import text
            _e = create_async_engine(settings.DATABASE_URL, pool_size=1, max_overflow=0)
            async with _e.connect() as conn:
                await conn.execute(text("SELECT 1"))
            await _e.dispose()
            result["dependencies"]["postgres"] = {
                "status": "ok",
                "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
            }
        except Exception as exc:
            result["dependencies"]["postgres"] = {"status": "error", "detail": str(exc)}
            overall_ok = False
    else:
        result["dependencies"]["postgres"] = {"status": "sqlite_dev"}

    # Redis
    if settings.REDIS_PASSWORD or settings.REDIS_HOST != "redis" or True:
        try:
            t0 = time.perf_counter()
            import redis.asyncio as aioredis
            r = aioredis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            await r.ping()
            await r.aclose()
            result["dependencies"]["redis"] = {
                "status": "ok",
                "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
            }
        except Exception as exc:
            result["dependencies"]["redis"] = {"status": "error", "detail": str(exc)}
            overall_ok = False

    # Evolution API (não-crítico — não derruba o status geral)
    if settings.EVOLUTION_SERVER_URL:
        try:
            t0 = time.perf_counter()
            import httpx
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{settings.EVOLUTION_SERVER_URL.rstrip('/')}/")
            result["dependencies"]["evolution_api"] = {
                "status": "ok" if res.status_code < 500 else "degraded",
                "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                "http_status": res.status_code,
            }
        except Exception as exc:
            result["dependencies"]["evolution_api"] = {"status": "unreachable", "detail": str(exc)}
    else:
        result["dependencies"]["evolution_api"] = {"status": "not_configured"}

    if not overall_ok:
        result["status"] = "degraded"

    return JSONResponse(content=result, status_code=200 if overall_ok else 503)


# ── Routers ────────────────────────────────────────────────────────────────
from src.api.ai_config import ai_config_router
from src.api.apikeys import apikey_router
from src.api.auth import auth_router
from src.api.automations import automation_router
from src.api.butler import butler_router
from src.api.leads import leads_router
from src.api.locales import locale_router
from src.api.master_admin import master_router
from src.api.metrics import metrics_router
from src.api.mfa import mfa_router
from src.api.notifications import notification_router
from src.api.preferences import pref_router
from src.api.products import router as products_router
from src.api.reports import report_router
from src.api.roles import role_router
from src.api.routes import api_router
from src.api.system_config import system_config_router
from src.api.tenant import tenant_router
from src.api.tenant_quota import quota_router
from src.api.usage import billing_router, usage_router
from src.api.webhooks import webhooks_router
from src.api.workflow import workflow_router
from src.api.onboarding import router as onboarding_router
from src.api.agent_profile_editor import router as agent_profile_router
from src.api.billing_stripe import router as stripe_router

app.include_router(auth_router,           prefix=f"{settings.API_V1_STR}/auth",          tags=["auth"])
app.include_router(mfa_router,            prefix=f"{settings.API_V1_STR}/auth/mfa",      tags=["mfa"])
app.include_router(tenant_router,         prefix=f"{settings.API_V1_STR}/tenant",        tags=["tenant"])
app.include_router(role_router,           prefix=f"{settings.API_V1_STR}/roles",         tags=["roles"])
app.include_router(pref_router,           prefix=f"{settings.API_V1_STR}/preferences",   tags=["preferences"])
app.include_router(locale_router,         prefix=f"{settings.API_V1_STR}/locales",       tags=["locales"])
app.include_router(automation_router,     prefix=f"{settings.API_V1_STR}/automations",   tags=["automations"])
app.include_router(notification_router,   prefix=f"{settings.API_V1_STR}/notifications", tags=["notifications"])
app.include_router(apikey_router,         prefix=f"{settings.API_V1_STR}/apikeys",       tags=["apikeys"])
app.include_router(report_router,         prefix=f"{settings.API_V1_STR}/reports",       tags=["reports"])
app.include_router(ai_config_router,      prefix=f"{settings.API_V1_STR}/ai-config",     tags=["ai-config"])
app.include_router(usage_router,          prefix=f"{settings.API_V1_STR}/usage",         tags=["usage"])
app.include_router(billing_router,        prefix=f"{settings.API_V1_STR}/billing",       tags=["billing"])
app.include_router(workflow_router,       prefix=f"{settings.API_V1_STR}/workflow",      tags=["workflow"])
app.include_router(master_router,         prefix=f"{settings.API_V1_STR}/master",        tags=["master-admin"])
app.include_router(leads_router,          prefix=f"{settings.API_V1_STR}/master",        tags=["master-leads"])
app.include_router(quota_router,          prefix=f"{settings.API_V1_STR}/master",        tags=["master-quotas"])
app.include_router(butler_router,         prefix=f"{settings.API_V1_STR}/master",        tags=["butler-agent"])
app.include_router(webhooks_router,       prefix=f"{settings.API_V1_STR}/webhooks",      tags=["webhooks"])
app.include_router(products_router,                                                       tags=["products"])
app.include_router(metrics_router,        prefix=f"{settings.API_V1_STR}",               tags=["observability"])
app.include_router(system_config_router,  prefix=f"{settings.API_V1_STR}/master",        tags=["system-config"])
app.include_router(api_router,            prefix=settings.API_V1_STR)
app.include_router(onboarding_router)
app.include_router(agent_profile_router)
app.include_router(stripe_router)


# ── Legacy fallback ────────────────────────────────────────────────────────
@app.post("/api/auth/token", tags=["auth"], include_in_schema=False)
async def legacy_token_fallback(request: Request):
    logger.warning("Legacy auth endpoint called.")
    raise HTTPException(
        status_code=307,
        detail="Please use /api/v1/auth/token",
        headers={"Location": f"{settings.API_V1_STR}/auth/token"},
    )


# ── Static files + page routes ─────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
frontend_path = (
    os.path.join(os.path.dirname(BASE_DIR), "frontend")
    if os.path.basename(BASE_DIR) == "src"
    else os.path.join(BASE_DIR, "frontend")
)

if os.path.exists(frontend_path):
    logger.info(f"Frontend: {frontend_path}")

    for folder in ["css", "js", "assets", "img"]:
        fp = os.path.join(frontend_path, folder)
        if os.path.exists(fp):
            app.mount(f"/{folder}", StaticFiles(directory=fp), name=folder)

    app.mount("/static", StaticFiles(directory=frontend_path), name="static_old")

    def _page(filename: str):
        """Return a FileResponse for a frontend HTML page, or 404."""
        path = os.path.join(frontend_path, filename)
        if os.path.exists(path):
            return FileResponse(path)
        raise HTTPException(status_code=404, detail=f"{filename} not found")

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        p = os.path.join(frontend_path, "favicon.ico")
        return FileResponse(p, media_type="image/x-icon") if os.path.exists(p) else Response(status_code=204)

    @app.get("/robots.txt", include_in_schema=False)
    async def robots_txt():
        p = os.path.join(frontend_path, "robots.txt")
        if os.path.exists(p):
            return FileResponse(p, media_type="text/plain")
        public_url = (settings.PUBLIC_URL or "").rstrip("/")
        return PlainTextResponse(
            f"User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /admin\nDisallow: /master\n\nSitemap: {public_url}/sitemap.xml\n"
        )

    @app.get("/sitemap.xml", include_in_schema=False)
    async def sitemap_xml():
        public_url = (settings.PUBLIC_URL or "").rstrip("/")
        content = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f'  <url><loc>{public_url}/</loc><changefreq>weekly</changefreq><priority>1.0</priority></url>\n'
            f'  <url><loc>{public_url}/login</loc><changefreq>monthly</changefreq><priority>0.8</priority></url>\n'
            f'  <url><loc>{public_url}/termos</loc><changefreq>yearly</changefreq><priority>0.3</priority></url>\n'
            f'  <url><loc>{public_url}/privacidade</loc><changefreq>yearly</changefreq><priority>0.3</priority></url>\n'
            f'  <url><loc>{public_url}/lgpd</loc><changefreq>yearly</changefreq><priority>0.3</priority></url>\n'
            '</urlset>'
        )
        return Response(content=content, media_type="application/xml")

    @app.get("/",           include_in_schema=False)
    async def landing_page():    return _page("home.html") if os.path.exists(os.path.join(frontend_path, "home.html")) else _page("login.html")

    @app.get("/login",      include_in_schema=False)
    @app.get("/login.html", include_in_schema=False)
    async def login_page():      return _page("login.html")

    @app.get("/admin",      include_in_schema=False)
    @app.get("/dashboard",  include_in_schema=False)
    async def admin_dashboard(): return _page("index.html")

    @app.get("/master",     include_in_schema=False)
    @app.get("/master.html",include_in_schema=False)
    async def master_portal():   return _page("master.html")

    @app.get("/client",     include_in_schema=False)
    @app.get("/client.html",include_in_schema=False)
    async def client_portal():   return _page("client.html")

    @app.get("/home.html",  include_in_schema=False)
    async def home_html():       return _page("home.html")

    @app.get("/onboarding", include_in_schema=False)
    async def onboarding_page():
        p = os.path.join(frontend_path, "onboarding.html")
        return FileResponse(p) if os.path.exists(p) else _page("login.html")

    @app.get("/status",     include_in_schema=False)
    async def status_page():
        p = os.path.join(frontend_path, "status.html")
        return FileResponse(p) if os.path.exists(p) else RedirectResponse(url="/health")

else:
    logger.warning(f"Frontend directory not found at {frontend_path}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
