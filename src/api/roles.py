from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import List, Annotated
from src.schemas import RoleCreate, RoleUpdate, RoleResponse
from src.services.role_service import role_service
from src.api.auth import get_current_user, RequirePermissions
from src.models.admin import AdminUser
from src.models.database import async_session

role_router = APIRouter()

@role_router.get("/", response_model=List[RoleResponse])
async def list_roles(
    current_user: Annotated[AdminUser, Depends(RequirePermissions(["roles:read"]))]
):
    """
    List all roles for the current tenant.
    Requires 'roles:read' permission (or '*').
    """
    roles = await role_service.list_roles(tenant_id=current_user.tenant_id)
    return [RoleResponse.model_validate(r) for r in roles]

@role_router.post("/", response_model=RoleResponse)
async def create_role(
    data: RoleCreate,
    current_user: Annotated[AdminUser, Depends(RequirePermissions(["roles:write"]))]
):
    """
    Create a new role for the current tenant.
    Requires 'roles:write' permission.
    """
    role = await role_service.create_role(data, tenant_id=current_user.tenant_id, operator=current_user)
    return RoleResponse.model_validate(role)

@role_router.put("/{role_id}", response_model=RoleResponse)
async def update_role(
    request: Request,
    role_id: int,
    data: RoleUpdate,
    current_user: Annotated[AdminUser, Depends(RequirePermissions(["roles:write"]))]
):
    """
    Update an existing role. Requires 'roles:write' permission and MFA.
    """
    if current_user.mfa_enabled:
        from src.services.mfa_service import mfa_service
        mfa_token = request.headers.get("X-MFA-Token")
        if not mfa_token:
            raise HTTPException(status_code=403, detail="MFA token required for sensitive operations")
        
        async with async_session() as session:
            is_valid = await mfa_service.verify_totp(current_user.id, mfa_token, session)
        if not is_valid:
            raise HTTPException(status_code=403, detail="Invalid MFA token")

    role = await role_service.update_role(role_id, data, tenant_id=current_user.tenant_id, operator=current_user)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found or cannot be modified.")
    return RoleResponse.model_validate(role)

@role_router.delete("/{role_id}")
async def delete_role(
    role_id: int,
    current_user: Annotated[AdminUser, Depends(RequirePermissions(["roles:write"]))]
):
    """
    Delete a role.
    Requires 'roles:write' permission.
    """
    success = await role_service.delete_role(role_id, tenant_id=current_user.tenant_id, operator=current_user)
    if not success:
        raise HTTPException(status_code=400, detail="Role not found or is a system role.")
    return {"status": "deleted"}
