import logging
import os
import secrets
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from src.config import settings
from src.middleware.metrics import PrometheusMetricsMiddleware
from src.middleware.performance import PerformanceMiddleware
from src.middleware.rate_limit_middleware import RateLimitMiddleware
from src.middleware.request_id import RequestIDMiddleware
from src.middleware.tenant_context import TenantContextMiddleware

# -------------------------------------------------------------------------
# CRITICAL FIX: Force UTF-8 encoding for Windows Console
# -------------------------------------------------------------------------
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ── Lifespan (replaces deprecated @app.on_event) ─────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── STARTUP ──────────────────────────────────────────────────────────
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

    # ── Alembic / create_all ───────────────────────────────────────────────
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
                existing = [
                    col["name"] for col in inspector.get_columns("evolution_instances")
                ]
                migrations_to_run = []
                if "evolution_ip" not in existing:
                    migrations_to_run.append(
                        "ALTER TABLE evolution_instances ADD COLUMN evolution_ip VARCHAR"
                    )
                if "owner_email" not in existing:
                    migrations_to_run.append(
                        "ALTER TABLE evolution_instances ADD COLUMN owner_email VARCHAR"
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
                'Generate one with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
            )
        else:
            logger.warning("⚠️  ENCRYPTION_KEY env variable is not set.")
    else:
        logger.info("✅ ENCRYPTION_KEY is set. AI Config key vault active.")

    if settings.TELEGRAM_BOT_TOKEN and settings.PUBLIC_URL:
        from src.services.telegram_service import telegram_service

        webhook_url = (
            f"{settings.PUBLIC_URL.rstrip('/')}{settings.API_V1_STR}/webhooks/telegram"
        )
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
    logger.info("✅ Butler Agent scheduler started with 8 background jobs.")
    logger.info("✅ TenantContextMiddleware ativo — multi-tenant seguro.")
    logger.info("✅ PerformanceMiddleware ativo — Server-Timing headers.")
    logger.info("✅ RequestIDMiddleware ativo — X-Request-ID tracing.")
    logger.info("✅ Onboarding: /api/onboarding/*")
    logger.info("✅ Agent Profile Editor: /api/v1/agent/profile/*")
    logger.info("✅ Stripe Billing: /api/v1/stripe/*")
    logger.info(
        "✅ Landing: / → home.html | Admin: /admin | Client: /client | Master: /master"
    )

    try:
        from src.scripts.create_master_admin import ensure_master_admin

        _seed_engine = create_async_engine(settings.DATABASE_URL, echo=False)
        _SeedSession = sessionmaker(
            _seed_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with _SeedSession() as _seed_session:
            await ensure_master_admin(_seed_session, reset_password=False)
        await _seed_engine.dispose()
        logger.info("✅ Master admin verificado/criado com sucesso.")
    except Exception as _e:
        logger.warning(f"⚠️ Auto-seed master admin falhou: {_e}")

    yield  # ── app is running ──

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

# ── Middleware order (applied bottom-up by Starlette) ────────────────────
# Outermost (runs first on request, last on response):
app.add_middleware(RequestIDMiddleware)       # 1. inject X-Request-ID
app.add_middleware(PerformanceMiddleware)     # 2. Server-Timing + slow log
app.add_middleware(TenantContextMiddleware)   # 3. multi-tenant guard
app.add_middleware(PrometheusMetricsMiddleware) # 4. prometheus
app.add_middleware(RateLimitMiddleware)       # 5. rate limiting (innermost)

if getattr(settings, "APP_DEBUG", False):
    @app.middleware("http")
    async def add_no_cache_header(request: Request, call_next):
        response = await call_next(request)
        if (
            request.url.path.endswith(".html")
            or request.url.path.endswith(".js")
            or request.url.path.endswith(".css")
        ):
            response.headers["Cache-Control"] = (
                "no-store, no-cache, must-revalidate, max-age=0"
            )
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

if settings.BACKEND_CORS_ORIGINS:
    origins = list(settings.BACKEND_CORS_ORIGINS)
    if settings.PUBLIC_URL:
        p_url = settings.PUBLIC_URL.rstrip("/")
        if p_url not in origins:
            origins.append(p_url)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _inject_csp_nonce(html_content: str, nonce: str) -> str:
    """Inject nonce attribute into all <script> and <style> tags in HTML content."""
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
        connect_origins.append(f"https://{public_domain}")
        connect_origins.append(f"wss://{public_domain}")

    # NOTE: cdn.tailwindcss.com removed — Tailwind is now compiled locally.
    # If still using CDN in any HTML during migration, add it back temporarily.
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


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["observability"])
async def health_check():
    """Dependency health check — DB, Redis, Evolution API."""
    import time
    import asyncio

    result = {
        "status": "ok",
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "dependencies": {},
    }
    overall_ok = True

    # ── PostgreSQL ──────────────────────────────────────────────────────────
    try:
        t0 = time.perf_counter()
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy import text
        _engine = create_async_engine(settings.DATABASE_URL, pool_size=1)
        async with _engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        await _engine.dispose()
        result["dependencies"]["postgres"] = {
            "status": "ok",
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
        }
    except Exception as e:
        result["dependencies"]["postgres"] = {"status": "error", "detail": str(e)}
        overall_ok = False

    # ── Redis ───────────────────────────────────────────────────────────────
    try:
        t0 = time.perf_counter()
        import redis.asyncio as aioredis
        r = aioredis.Redis(
            host=getattr(settings, "REDIS_HOST", "redis"),
            port=int(getattr(settings, "REDIS_PORT", 6379)),
            password=getattr(settings, "REDIS_PASSWORD", None),
            socket_connect_timeout=2,
        )
        await r.ping()
        await r.aclose()
        result["dependencies"]["redis"] = {
            "status": "ok",
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
        }
    except Exception as e:
        result["dependencies"]["redis"] = {"status": "error", "detail": str(e)}
        overall_ok = False

    # ── Evolution API ───────────────────────────────────────────────────
    evolution_url = getattr(settings, "EVOLUTION_SERVER_URL", None)
    if evolution_url:
        try:
            t0 = time.perf_counter()
            import httpx
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{evolution_url.rstrip('/')}/")
            result["dependencies"]["evolution_api"] = {
                "status": "ok" if res.status_code < 500 else "degraded",
                "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                "http_status": res.status_code,
            }
        except Exception as e:
            result["dependencies"]["evolution_api"] = {"status": "error", "detail": str(e)}
            # Evolution being down is non-critical for the app itself
    else:
        result["dependencies"]["evolution_api"] = {"status": "not_configured"}

    if not overall_ok:
        result["status"] = "degraded"

    status_code = 200 if overall_ok else 503
    from fastapi.responses import JSONResponse
    return JSONResponse(content=result, status_code=status_code)


# ── Routers ──────────────────────────────────────────────────────────────────
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
app.include_router(ai_config_router, prefix=f"{settings.API_V1_STR}/ai-config", tags=["ai-config"])
app.include_router(usage_router, prefix=f"{settings.API_V1_STR}/usage", tags=["usage"])
app.include_router(billing_router, prefix=f"{settings.API_V1_STR}/billing", tags=["billing"])
app.include_router(workflow_router, prefix=f"{settings.API_V1_STR}/workflow", tags=["workflow"])
app.include_router(master_router, prefix=f"{settings.API_V1_STR}/master", tags=["master-admin"])
app.include_router(leads_router, prefix=f"{settings.API_V1_STR}/master", tags=["master-leads"])
app.include_router(quota_router, prefix=f"{settings.API_V1_STR}/master", tags=["master-quotas"])
app.include_router(butler_router, prefix=f"{settings.API_V1_STR}/master", tags=["butler-agent"])
app.include_router(webhooks_router, prefix=f"{settings.API_V1_STR}/webhooks", tags=["webhooks"])
app.include_router(products_router, tags=["products"])
app.include_router(metrics_router, prefix=f"{settings.API_V1_STR}", tags=["observability"])
app.include_router(system_config_router, prefix=f"{settings.API_V1_STR}/master", tags=["system-config"])
app.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(onboarding_router)
app.include_router(agent_profile_router)
app.include_router(stripe_router)


# --- Legacy Fallback ---
@app.post("/api/auth/token", tags=["auth"], include_in_schema=False)
async def legacy_token_fallback(request: Request):
    logger.warning("Legacy auth endpoint called.")
    raise HTTPException(
        status_code=307,
        detail="Please use /api/v1/auth/token",
        headers={"Location": f"{settings.API_V1_STR}/auth/token"},
    )


# ── Frontend static files ───────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(BASE_DIR) == "src":
    frontend_path = os.path.join(os.path.dirname(BASE_DIR), "frontend")
else:
    frontend_path = os.path.join(BASE_DIR, "frontend")

if os.path.exists(frontend_path):
    logger.info(f"Frontend directory identified at {frontend_path}")

    for folder in ["css", "js", "assets", "img"]:
        folder_path = os.path.join(frontend_path, folder)
        if os.path.exists(folder_path):
            app.mount(f"/{folder}", StaticFiles(directory=folder_path), name=folder)
            logger.info(f"✅ Mounted /{folder} from {folder_path}")

    app.mount("/static", StaticFiles(directory=frontend_path), name="static_old")

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        favicon_path = os.path.join(frontend_path, "favicon.ico")
        if os.path.exists(favicon_path):
            return FileResponse(favicon_path, media_type="image/x-icon")
        # Return 204 instead of broken HTML as favicon
        from fastapi.responses import Response
        return Response(status_code=204)

    @app.get("/robots.txt", include_in_schema=False)
    async def robots_txt():
        robots_path = os.path.join(frontend_path, "robots.txt")
        if os.path.exists(robots_path):
            return FileResponse(robots_path, media_type="text/plain")
        from fastapi.responses import PlainTextResponse
        public_url = getattr(settings, "PUBLIC_URL", "").rstrip("/")
        return PlainTextResponse(
            f"User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /admin\nDisallow: /master\n\nSitemap: {public_url}/sitemap.xml\n"
        )

    @app.get("/sitemap.xml", include_in_schema=False)
    async def sitemap_xml():
        public_url = getattr(settings, "PUBLIC_URL", "").rstrip("/")
        from fastapi.responses import Response
        content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>{public_url}/</loc><changefreq>weekly</changefreq><priority>1.0</priority></url>
  <url><loc>{public_url}/login</loc><changefreq>monthly</changefreq><priority>0.8</priority></url>
  <url><loc>{public_url}/termos</loc><changefreq>yearly</changefreq><priority>0.3</priority></url>
  <url><loc>{public_url}/privacidade</loc><changefreq>yearly</changefreq><priority>0.3</priority></url>
  <url><loc>{public_url}/lgpd</loc><changefreq>yearly</changefreq><priority>0.3</priority></url>
</urlset>"""
        return Response(content=content, media_type="application/xml")

    @app.get("/login.html", include_in_schema=False)
    async def login_html_page():
        login_path = os.path.join(frontend_path, "login.html")
        if os.path.exists(login_path):
            return FileResponse(login_path)
        raise HTTPException(status_code=404, detail="Login page not found")

    @app.get("/login", include_in_schema=False)
    async def login_page():
        login_path = os.path.join(frontend_path, "login.html")
        if os.path.exists(login_path):
            return FileResponse(login_path)
        raise HTTPException(status_code=404, detail="Login page not found")

    @app.get("/admin", include_in_schema=False)
    async def admin_dashboard():
        return FileResponse(os.path.join(frontend_path, "index.html"))

    @app.get("/dashboard", include_in_schema=False)
    async def dashboard_alias():
        return FileResponse(os.path.join(frontend_path, "index.html"))

    @app.get("/master.html", include_in_schema=False)
    async def master_portal():
        master_path = os.path.join(frontend_path, "master.html")
        if os.path.exists(master_path):
            return FileResponse(master_path)
        raise HTTPException(status_code=404, detail="Master portal not found")

    @app.get("/master", include_in_schema=False)
    async def master_portal_alias():
        master_path = os.path.join(frontend_path, "master.html")
        if os.path.exists(master_path):
            return FileResponse(master_path)
        raise HTTPException(status_code=404, detail="Master portal not found")

    @app.get("/client.html", include_in_schema=False)
    async def client_portal():
        client_path = os.path.join(frontend_path, "client.html")
        if os.path.exists(client_path):
            return FileResponse(client_path)
        raise HTTPException(status_code=404, detail="Client portal not found")

    @app.get("/client", include_in_schema=False)
    async def client_portal_alias():
        client_path = os.path.join(frontend_path, "client.html")
        if os.path.exists(client_path):
            return FileResponse(client_path)
        raise HTTPException(status_code=404, detail="Client portal not found")

    @app.get("/home.html", include_in_schema=False)
    async def home_html_page():
        home_path = os.path.join(frontend_path, "home.html")
        if os.path.exists(home_path):
            return FileResponse(home_path)
        raise HTTPException(status_code=404, detail="Home page not found")

    @app.get("/onboarding", include_in_schema=False)
    async def onboarding_page():
        onboarding_path = os.path.join(frontend_path, "onboarding.html")
        if os.path.exists(onboarding_path):
            return FileResponse(onboarding_path)
        return FileResponse(os.path.join(frontend_path, "login.html"))

    @app.get("/status", include_in_schema=False)
    async def status_page():
        status_path = os.path.join(frontend_path, "status.html")
        if os.path.exists(status_path):
            return FileResponse(status_path)
        # Redirect to /health JSON if no status page yet
        return RedirectResponse(url="/health")

    @app.get("/", include_in_schema=False)
    async def landing_page():
        home_path = os.path.join(frontend_path, "home.html")
        if os.path.exists(home_path):
            return FileResponse(home_path)
        login_path = os.path.join(frontend_path, "login.html")
        if os.path.exists(login_path):
            return FileResponse(login_path)
        raise HTTPException(status_code=404, detail="Home page not found")

else:
    logger.warning(f"Frontend directory not found at {frontend_path}")


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
