"""
Main Application Entry Point
Antigravity Skill: framework-setup
"""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config.settings import get_settings
from app.api.whatsapp.routes import router as whatsapp_router
from app.api.dashboard.routes import router as dashboard_router
from app.utils.logger import get_logger

settings = get_settings()
logger = get_logger(__name__)

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug
)

# CORS Configuration
# Allow frontend dev server (usually 5173 for Vite) and production
origins = [
    "http://localhost:5173",
    "http://localhost:5000",
    "http://127.0.0.1:5173",
    "*" # For dev simplicity, creating explicit list is better for prod
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Rotas
app.include_router(whatsapp_router, prefix="/api/v1", tags=["whatsapp"])
app.include_router(dashboard_router, prefix="/api/v1/dashboard", tags=["dashboard"])

@app.get("/health")
async def health_check():
    return {"status": "ok", "version": settings.app_version}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
