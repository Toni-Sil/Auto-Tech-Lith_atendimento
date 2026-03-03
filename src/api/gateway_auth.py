from fastapi import HTTPException, status, Depends, Security
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import get_db
from src.models.api_key import ApiKey
from src.services.api_key_service import api_key_service

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_gateway_api_key(
    api_key_header: str = Security(api_key_header),
    db: AsyncSession = Depends(get_db)
) -> ApiKey:
    """
    Dependency used strictly by API Gateway endpoints that allow external consumption.
    Validates the X-API-Key header against the database.
    """
    if not api_key_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API Key header",
            headers={"WWW-Authenticate": "ApiKey"},
        )
        
    api_key = await api_key_service.verify_api_key(db, api_key_header)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API Key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
        
    return api_key
