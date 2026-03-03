from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
import json
import os

from src.utils.logger import setup_logger

logger = setup_logger(__name__)
locale_router = APIRouter()

LOCALES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "locales")

@locale_router.get("/{lang}")
async def get_locale(lang: str):
    """
    Fetch the JSON dictionary for the specified language code.
    Fallback to pt-BR if not found.
    Ex: /api/v1/locales/en-US
    """
    # Sanitize input to prevent path traversal
    safe_lang = os.path.basename(lang)
    if not safe_lang.endswith(".json"):
        safe_lang += ".json"
        
    file_path = os.path.join(LOCALES_DIR, safe_lang)
    
    if not os.path.exists(file_path):
        # Fallback
        logger.warning(f"Locale {lang} not found. Falling back to pt-BR.")
        file_path = os.path.join(LOCALES_DIR, "pt-BR.json")
        
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Locale not found")
            
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return JSONResponse(content=data)
    except Exception as e:
        logger.error(f"Error reading locale {file_path}: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
