from fastapi import APIRouter, Request, Depends, HTTPException, status
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.database import get_db
from src.models.tenant import Tenant
from src.models.admin import AdminUser
from src.schemas import TenantRegistrationRequest, VerifyPhoneRequest
from src.schemas import VerifyEmailRequest # assuming I added this earlier to schemas
from src.utils.security import get_password_hash
from src.utils.rate_limit import rate_limit_check
from src.utils.audit import log_security_event
from src.utils.security import create_access_token
from datetime import timedelta
from src.config import settings
from src.utils.logger import setup_logger
import random
import re

logger = setup_logger(__name__)
tenant_router = APIRouter()

@tenant_router.get("/resolve")
async def resolve_tenant(request: Request, host: str = None, db: AsyncSession = Depends(get_db)):
    """
    Public endpoint to resolve standard branding and information for a tenant
    Based on the custom domain or subdomain from the request host.
    """
    target_host = host or request.headers.get("host", "")
    
    # Clean port
    domain = target_host.split(":")[0]
    
    # Try custom domain first, then subdomain
    stmt = select(Tenant).where(
        Tenant.is_active == True,
        or_(
            Tenant.custom_domain == domain,
            Tenant.subdomain == domain.split(".")[0]  # rough subdomain extraction
        )
    )
    tenant = await db.scalar(stmt)
    
    if not tenant:
        # Fallback to default tenant (id=1)
        tenant = await db.get(Tenant, 1)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
            
    return {
        "id": tenant.id,
        "name": tenant.name,
        "primary_color": tenant.primary_color,
        "logo_url": tenant.logo_url,
    }

@tenant_router.post("/register")
async def register_tenant(
    request: Request,
    reg_data: TenantRegistrationRequest,
    db: AsyncSession = Depends(get_db)
):
    await rate_limit_check(request, limit=5, window_seconds=3600)

    if not re.match("^[a-z0-9-]+$", reg_data.subdomain):
        raise HTTPException(status_code=400, detail="Subdomínio inválido.")

    existing_tenant = await db.scalar(select(Tenant).where(Tenant.subdomain == reg_data.subdomain))
    if existing_tenant:
        raise HTTPException(status_code=400, detail="Subdomínio já está em uso.")
        
    existing_admin = await db.scalar(select(AdminUser).where(or_(
        AdminUser.username == reg_data.admin_email,
        AdminUser.email == reg_data.admin_email
    )))
    if existing_admin:
        raise HTTPException(status_code=400, detail="E-mail já está em uso.")

    try:
        new_tenant = Tenant(
            name=reg_data.name,
            subdomain=reg_data.subdomain
        )
        db.add(new_tenant)
        await db.flush() # Get ID without committing

        import string
        import secrets
        random_code = ''.join(secrets.choice(string.digits) for _ in range(6))

        new_admin = AdminUser(
            tenant_id=new_tenant.id,
            username=reg_data.admin_email,
            email=reg_data.admin_email,
            name=reg_data.admin_name,
            phone=reg_data.admin_phone,
            password_hash=get_password_hash(reg_data.admin_password),
            role="owner",
            access_code=random_code, # Satisfy DB constraint
            email_verified=False,
            phone_verified=False
        )
        db.add(new_admin)
        
        # Email Verification Token
        verify_token = create_access_token(
            data={"sub": new_admin.username, "purpose": "email_verification"},
            expires_delta=timedelta(hours=24)
        )
        
        # Phone Verification OTP
        otp = str(random.randint(100000, 999999))
        new_admin.phone_otp = get_password_hash(otp)
        
        await db.commit()
        
        logger.info(f"✅ Tenant registered: {new_tenant.name} ({new_tenant.subdomain})")
        logger.info(f"📧 Verification link for {new_admin.email}: /api/v1/tenant/verify-email?token={verify_token}")
        logger.info(f"📱 OTP for {new_admin.phone}: {otp}")
        logger.info(f"🔑 Temporary Access Code: {random_code}")

    except Exception as e:
        await db.rollback()
        logger.error(f"FATAL ERROR during tenant registration: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")

    return {
        "message": "Tenant registrado com sucesso. Verifique seu e-mail e celular.", 
        "tenant_id": new_tenant.id
    }

from jose import JWTError, jwt
from src.utils.security import verify_password

@tenant_router.post("/verify-email")
async def verify_tenant_email(
    request: Request,
    verification: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db)
):
    await rate_limit_check(request, limit=10, window_seconds=3600)
    try:
        payload = jwt.decode(verification.token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        token_username = payload.get("sub")
        purpose = payload.get("purpose")
        if purpose != "email_verification" or not token_username:
            raise HTTPException(status_code=400, detail="Token inválido.")
    except JWTError:
        raise HTTPException(status_code=400, detail="Token inválido ou expirado.")

    admin = await db.scalar(select(AdminUser).where(AdminUser.username == token_username))
    if not admin:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    
    admin.email_verified = True
    await log_security_event(db, "registration_email_verified", username=admin.username, tenant_id=admin.tenant_id, ip_address=request.client.host)
    await db.commit()
    
    return {"message": "E-mail verificado com sucesso."}

@tenant_router.post("/verify-phone")
async def verify_tenant_phone(
    request: Request,
    data: VerifyPhoneRequest,
    db: AsyncSession = Depends(get_db)
):
    await rate_limit_check(request, limit=10, window_seconds=3600)
    
    admin = await db.scalar(select(AdminUser).where(AdminUser.phone == data.phone))
    if not admin or not admin.phone_otp:
        raise HTTPException(status_code=404, detail="Solicitação de OTP não encontrada para este telefone.")
        
    if not verify_password(data.otp, admin.phone_otp):
        await log_security_event(db, "registration_phone_verify_failed", username=admin.username, tenant_id=admin.tenant_id, ip_address=request.client.host)
        raise HTTPException(status_code=400, detail="OTP inválido.")
        
    admin.phone_verified = True
    admin.phone_otp = None
    await log_security_event(db, "registration_phone_verified", username=admin.username, tenant_id=admin.tenant_id, ip_address=request.client.host)
    await db.commit()
    
    return {"message": "Telefone verificado com sucesso."}
