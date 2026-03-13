from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import RequirePermissions, get_current_user
from src.models.admin import AdminUser
from src.models.database import get_db
from src.schemas.api_key import (ApiKeyCreate, ApiKeyCreationResponse,
                                 ApiKeyResponse)
from src.services.api_key_service import api_key_service

apikey_router = APIRouter()


@apikey_router.post("", response_model=ApiKeyCreationResponse)
async def create_api_key(
    data: ApiKeyCreate,
    current_user: Annotated[AdminUser, Depends(RequirePermissions(["settings:write"]))],
    db: AsyncSession = Depends(get_db),
):
    """
    Creates a new API Key for external integrations.
    Returns the plain_text key ONLY ONCE. The client must save it immediately.
    """
    key_obj, plain_key = await api_key_service.create_api_key(
        db, current_user.tenant_id, data
    )

    # We adapt the DB object into our response model, appending the plain_key
    # We use model_dump to create a dict and then add the plain_key
    key_data = ApiKeyResponse.model_validate(key_obj).model_dump()
    return ApiKeyCreationResponse(**key_data, plain_key=plain_key)


@apikey_router.get("", response_model=List[ApiKeyResponse])
async def list_api_keys(
    current_user: Annotated[AdminUser, Depends(RequirePermissions(["settings:read"]))],
    db: AsyncSession = Depends(get_db),
):
    """List all API Keys for the tenant."""
    return await api_key_service.get_api_keys(db, current_user.tenant_id)


@apikey_router.delete("/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    api_key_id: int,
    current_user: Annotated[AdminUser, Depends(RequirePermissions(["settings:write"]))],
    db: AsyncSession = Depends(get_db),
):
    """Deletes/Revokes an API Key."""
    success = await api_key_service.delete_api_key(
        db, current_user.tenant_id, api_key_id
    )
    if not success:
        raise HTTPException(status_code=404, detail="API Key not found")
    return None
