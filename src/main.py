import sys
import os

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

from contextlib import asynccontextmanager

# Configuração de Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# Configuração de CORS
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Montar arquivos estáticos do frontend (Dashboard) será feito no final

@app.get("/health")
async def health_check():
    return {"status": "ok", "project": settings.PROJECT_NAME, "version": settings.VERSION}

# Importar rotas da API aqui posteriormente
# Importar rotas da API aqui posteriormente
from src.api.routes import api_router
from src.api.auth import auth_router

app.include_router(auth_router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
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
    # Start Telegram Bot Worker in background
    import asyncio
    from src.workers.telegram_bot import telegram_bot_worker
    asyncio.create_task(telegram_bot_worker())
    logger.info("Startup: Telegram Worker launched.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
