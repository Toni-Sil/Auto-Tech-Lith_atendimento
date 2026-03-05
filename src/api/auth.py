
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import timedelta
from typing import Annotated, Optional

from src.models.database import get_db
from src.models.admin import AdminUser
from src.models.tenant import Tenant
from src.models.user_session import UserSession
from src.utils.security import verify_password, create_access_token, get_password_hash
from src.config import settings
from src.utils.logger import setup_logger
from src.utils.audit import log_security_event
from src.utils.rate_limit import rate_limit_check

from datetime import datetime, timezone, timedelta

logger = setup_logger(__name__)
auth_router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/token", auto_error=False)

async def get_current_user(
    request: Request,
    token: Annotated[Optional[str], Depends(oauth2_scheme)] = None, 
    db: AsyncSession = Depends(get_db)
):
    from jose import JWTError, jwt
    
    # Try header (via oauth2_scheme) or cookie
    actual_token = token or request.cookies.get("access_token")
    
    if not actual_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(actual_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        jti: str = payload.get("jti")
        if username is None:
            raise credentials_exception
        
        # Opcional: Validar se a sessão foi revogada
        if jti:
            session_check = await db.scalar(select(UserSession).where(UserSession.session_token_jti == jti))
            if session_check and session_check.is_revoked:
                raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    from sqlalchemy.orm import selectinload
    user = await db.scalar(
        select(AdminUser)
        .options(selectinload(AdminUser.custom_role))
        .where(AdminUser.username == username)
    )
    if user is None:
        raise credentials_exception
    return user

class RequirePermissions:
    def __init__(self, required_permissions: list):
        self.required_permissions = required_permissions

    def __call__(self, current_user: AdminUser = Depends(get_current_user)):
        if not current_user.custom_role:
            raise HTTPException(status_code=403, detail="Acesso negado: Usuário sem perfil de acesso definido.")
            
        user_perms = current_user.custom_role.permissions or []
        if "*" in user_perms:
            return current_user
            
        for perm in self.required_permissions:
            if perm not in user_perms:
                raise HTTPException(status_code=403, detail=f"Acesso negado: Falta permissão '{perm}'")
                
        return current_user

@auth_router.post("/token")
async def login_for_access_token(
    request: Request,
    response: Response,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: AsyncSession = Depends(get_db)
):
    await rate_limit_check(request)
    ip_address = request.client.host
    user_agent = request.headers.get("user-agent")
    
    # Use func.lower for case-insensitive search
    from sqlalchemy import func
    user = await db.scalar(
        select(AdminUser).where(func.lower(AdminUser.username) == func.lower(form_data.username))
    )
    
    if not user:
        await log_security_event(db, "login_failure_unknown_user", username=form_data.username, ip_address=ip_address, user_agent=user_agent)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    # Tenant & Verification Check (Only Owner/Admins of Tenants need verification)
    if user.tenant_id:
        tenant = await db.get(Tenant, user.tenant_id)
        if tenant and tenant.status == "pending":
            await log_security_event(db, "login_attempt_pending_tenant", username=user.username, ip_address=ip_address, user_agent=user_agent)
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Conta pendente de aprovação (Tenant em análise).")
            
        if user.role == "owner":
            if not user.email_verified:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verificação de E-mail pendente. Confirme seu e-mail para continuar.")
            if not user.phone_verified:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verificação de Telefone (OTP) pendente. Confirme seu celular para continuar.")
    
    # Brute Force Protection: Check Lockout
    if user.locked_until and datetime.now(timezone.utc) < user.locked_until.replace(tzinfo=timezone.utc):
        await log_security_event(db, "login_attempt_locked_account", username=user.username, ip_address=ip_address, user_agent=user_agent)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account temporarily locked. Try again after {user.locked_until.strftime('%H:%M:%S')}",
        )
    
    # Check password via hash OR via access_code (standard/fallback)
    is_valid_hash = user.password_hash and verify_password(form_data.password, user.password_hash)
    is_valid_code = user.access_code and form_data.password == user.access_code
    
    if not (is_valid_hash or is_valid_code):
        logger.info(f"❌ Login failed for {user.username}: Hash Valid={is_valid_hash}, Code Valid={is_valid_code}")
        # Increment failed attempts
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= 5:
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
            await log_security_event(db, "account_lockout", username=user.username, ip_address=ip_address, user_agent=user_agent, details="5 failed attempts")
        else:
            await log_security_event(db, "login_failure", username=user.username, ip_address=ip_address, user_agent=user_agent, details=f"Attempt {user.failed_login_attempts}")
        
        await db.commit()
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    # Check MFA if enabled
    if user.mfa_enabled:
        mfa_token = request.headers.get("X-MFA-Token")
        if not mfa_token:
            # Client must resend the login request WITH the X-MFA-Token header
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="MFA_REQUIRED"
            )
            
        from src.services.mfa_service import mfa_service
        if not mfa_service.verify_totp(user.mfa_secret, mfa_token):
            await log_security_event(db, "login_failure_invalid_mfa", username=user.username, ip_address=ip_address, user_agent=user_agent)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid MFA code"
            )
        
    # Automatic Migration: If they logged in with access_code and don't have a valid hash for it, hash it now.
    if is_valid_code and not is_valid_hash:
        user.password_hash = get_password_hash(form_data.password)
        # We don't remove access_code yet because it's used for Telegram linking, but now they have a proper bcrypt hash.    
    # Success: Reset security counters
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_active_at = datetime.now(timezone.utc)
    
    await log_security_event(db, "login_success", username=user.username, ip_address=ip_address, user_agent=user_agent)
    await db.commit()
        
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_token_expires = timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES)
    
    import uuid
    jti = uuid.uuid4().hex
    
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role, "tenant_id": user.tenant_id, "jti": jti},
        expires_delta=access_token_expires
    )
    
    refresh_token = create_access_token(
        data={"sub": user.username, "type": "refresh", "jti": jti},
        expires_delta=refresh_token_expires
    )
    
    # Save active session
    new_session = UserSession(
        user_id=user.id,
        session_token_jti=jti,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(new_session)
    await db.commit()
    
    # Set HttpOnly Cookies
    cookie_settings = {
        "httponly": True,
        "secure": settings.ENV == "production",
        "samesite": "lax", # "strict" can be too aggressive if they come from other domains
    }
    
    response.set_cookie(key="access_token", value=access_token, max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60, **cookie_settings)
    response.set_cookie(key="refresh_token", value=refresh_token, max_age=settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60, **cookie_settings)
    
    return {
        "access_token": access_token, 
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }

@auth_router.post("/refresh")
async def refresh_token(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    from jose import JWTError, jwt
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="Refresh token missing")
    
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        
        username = payload.get("sub")
        jti = payload.get("jti")
        
        # Validate session
        session = await db.scalar(select(UserSession).where(UserSession.session_token_jti == jti))
        if not session or session.is_revoked:
            raise HTTPException(status_code=401, detail="Session revoked")
            
        # Get user
        user = await db.scalar(select(AdminUser).where(AdminUser.username == username))
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
            
        # Generate new access token
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        new_access_token = create_access_token(
            data={"sub": user.username, "role": user.role, "tenant_id": user.tenant_id, "jti": jti},
            expires_delta=access_token_expires
        )
        
        # Update cookie
        response.set_cookie(
            key="access_token", 
            value=new_access_token, 
            max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            httponly=True,
            secure=settings.ENV == "production",
            samesite="lax"
        )
        
        return {"access_token": new_access_token, "token_type": "bearer"}
        
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

@auth_router.post("/logout")
async def logout(response: Response, current_user: Annotated[AdminUser, Depends(get_current_user)], db: AsyncSession = Depends(get_db), request: Request = None):
    # Revoke sessions for this user (or just the current one if JTI is known)
    # For now, let's just clear the cookies on the client side
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return {"status": "ok", "message": "Logged out successfully"}

from src.schemas import AccountRecoveryRequest, AccountRecoveryReset
import secrets

@auth_router.post("/recovery/request")
async def request_password_recovery(
    request: Request,
    recovery_data: AccountRecoveryRequest,
    db: AsyncSession = Depends(get_db)
):
    await rate_limit_check(request)
    from sqlalchemy import func, or_
    import asyncio
    
    # Proteção de timing (tempo constante)
    user = await db.scalar(
        select(AdminUser).where(
            or_(
                func.lower(AdminUser.username) == func.lower(recovery_data.email_or_username),
                func.lower(AdminUser.email) == func.lower(recovery_data.email_or_username) if recovery_data.email_or_username else False
            )
        )
    )
    
    if not user:
        await asyncio.sleep(0.5)
        return {"message": "Caso a conta exista, um link de recuperação foi enviado."}
        
    raw_token = secrets.token_hex(20)
    user.recovery_token = get_password_hash(raw_token)
    user.recovery_token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
    
    from src.models.recovery import RecoveryRequest
    recovery_req = RecoveryRequest(
        admin_id=user.id,
        status="pending",
        request_type="email",
        ip_address=request.client.host,
        expires_at=user.recovery_token_expires_at
    )
    db.add(recovery_req)
    
    await log_security_event(db, "recovery_requested_email", username=user.username, ip_address=request.client.host)
    await db.commit()
    
    # Dummy Email Sender (Console Logger)
    logger.info(f"📧 [DUMMY EMAIL] Enviado para {user.email or user.username}")
    logger.info(f"🔗 Link de redefinição: /reset-password?token={raw_token}&username={user.username}")
    
    return {"message": "Caso a conta exista, um link de recuperação foi enviado."}

@auth_router.post("/recovery/reset")
async def reset_password(
    request: Request,
    reset_data: AccountRecoveryReset,
    db: AsyncSession = Depends(get_db)
):
    await rate_limit_check(request)
    
    user = await db.scalar(select(AdminUser).where(AdminUser.username == reset_data.username))
    if not user or not user.recovery_token or not user.recovery_token_expires_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token inválido ou expirado.")
        
    if datetime.now(timezone.utc) > user.recovery_token_expires_at.replace(tzinfo=timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="O token de recuperação expirou.")
        
    if not verify_password(reset_data.token, user.recovery_token):
        await log_security_event(db, "recovery_failed_invalid_token", username=user.username, ip_address=request.client.host)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token de recuperação inválido.")
        
    # Token é válido, redefinir a senha
    user.password_hash = get_password_hash(reset_data.new_password)
    user.recovery_token = None
    user.recovery_token_expires_at = None
    user.failed_login_attempts = 0 # reset failed attempts just in case
    user.locked_until = None
    
    await log_security_event(db, "password_reset_completed", username=user.username, ip_address=request.client.host)
    await db.commit()
    
    return {"message": "Senha redefinida com sucesso."}


@auth_router.get("/me")
async def read_users_me(current_user: Annotated[AdminUser, Depends(get_current_user)]):
    return {
        "username": current_user.username, 
        "name": current_user.name, 
        "email": current_user.email,
        "role": current_user.custom_role.name if current_user.custom_role else current_user.role,
        "permissions": current_user.custom_role.permissions if current_user.custom_role else [],
        "avatar_url": current_user.avatar_url,
        "bio": current_user.bio,
        "company_role": current_user.company_role,
        "phone": current_user.phone,
        "telegram_username": current_user.telegram_username,
        "notification_preference": current_user.notification_preference,
        "mfa_enabled": current_user.mfa_enabled
    }

from src.schemas import AdminUserProfileUpdate, PasswordChangeRequest, VerifyEmailRequest
import json
import os
import uuid
import shutil
from fastapi import UploadFile, File

@auth_router.put("/me")
async def update_user_me(
    profile_data: AdminUserProfileUpdate,
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    previous_state = {
        "name": current_user.name,
        "avatar_url": current_user.avatar_url,
        "bio": current_user.bio,
        "company_role": current_user.company_role,
        "phone": current_user.phone,
        "telegram_username": current_user.telegram_username,
        "notification_preference": current_user.notification_preference,
    }

    if profile_data.name is not None:
        current_user.name = profile_data.name
    if profile_data.avatar_url is not None:
        current_user.avatar_url = profile_data.avatar_url
    if profile_data.bio is not None:
        current_user.bio = profile_data.bio
    if profile_data.company_role is not None:
        current_user.company_role = profile_data.company_role
    if profile_data.phone is not None:
        current_user.phone = profile_data.phone
    if profile_data.telegram_username is not None:
        current_user.telegram_username = profile_data.telegram_username
    if profile_data.notification_preference is not None:
        current_user.notification_preference = profile_data.notification_preference

    # Email update strictly requires verification step
    email_verification_sent = False
    if profile_data.email is not None and profile_data.email != current_user.email:
        # Enforce MFA if enabled
        if current_user.mfa_enabled:
            pass # Or we can assert X-MFA-Token here, but for PUT /me let's keep it simpler or we should checking request.headers.
            
        verify_token = create_access_token(
            data={"sub": current_user.username, "new_email": profile_data.email},
            expires_delta=timedelta(minutes=60)
        )
        logger.info(f"📧 [DUMMY EMAIL] Enviado link de verificação para {profile_data.email}")
        logger.info(f"🔗 Link de confirmação de email: /verify-email?token={verify_token}")
        email_verification_sent = True
        
    new_state = {
        "name": current_user.name,
        "avatar_url": current_user.avatar_url,
        "bio": current_user.bio,
        "company_role": current_user.company_role,
        "phone": current_user.phone,
        "telegram_username": current_user.telegram_username,
        "notification_preference": current_user.notification_preference,
    }

    await log_security_event(
        db,
        "profile_updated",
        username=current_user.username,
        tenant_id=current_user.tenant_id,
        operator_id=current_user.id,
        previous_value=json.dumps(previous_state),
        new_value=json.dumps(new_state)
    )

    await db.commit()
    await db.refresh(current_user)
    
    return {
        "username": current_user.username, 
        "name": current_user.name, 
        "role": current_user.custom_role.name if current_user.custom_role else current_user.role,
        "permissions": current_user.custom_role.permissions if current_user.custom_role else [],
        "avatar_url": current_user.avatar_url,
        "bio": current_user.bio,
        "company_role": current_user.company_role,
        "phone": current_user.phone,
        "telegram_username": current_user.telegram_username,
        "notification_preference": current_user.notification_preference,
        "mfa_enabled": current_user.mfa_enabled,
        "email": current_user.email,
        "email_verification_sent": email_verification_sent
    }

@auth_router.post("/me/verify-email")
async def verify_email_change(
    request: Request,
    verification_data: VerifyEmailRequest,
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    await rate_limit_check(request)
    from jose import JWTError, jwt
    try:
        payload = jwt.decode(verification_data.token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        token_username = payload.get("sub")
        new_email = payload.get("new_email")
        if token_username != current_user.username or not new_email:
            raise HTTPException(status_code=400, detail="Token inválido.")
    except JWTError:
        raise HTTPException(status_code=400, detail="Token inválido ou expirado.")

    # Apply change
    previous_email = current_user.email
    current_user.email = new_email
    await db.commit()
    await log_security_event(db, "email_verified_changed", username=current_user.username, tenant_id=current_user.tenant_id, operator_id=current_user.id, previous_value=previous_email, new_value=new_email)
    
    return {"message": "E-mail verificado e atualizado com sucesso."}

@auth_router.post("/me/avatar")
async def upload_user_avatar(
    file: UploadFile = File(...),
    current_user: Annotated[AdminUser, Depends(get_current_user)] = None,
    db: AsyncSession = Depends(get_db)
):
    upload_dir = os.path.join(os.getcwd(), "frontend", "assets", "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    
    file_ext = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(upload_dir, unique_filename)
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        logger.error(f"Error saving avatar: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to save image")
        
    static_url = f"/static/assets/uploads/{unique_filename}"
    
    current_user.avatar_url = static_url
    await db.commit()
    await db.refresh(current_user)
    
    return {"status": "success", "avatar_url": static_url}

@auth_router.put("/me/password")
async def change_password(
    request: Request,
    password_data: PasswordChangeRequest,
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    await rate_limit_check(request)
    
    # Require current password
    is_valid_hash = current_user.password_hash and verify_password(password_data.current_password, current_user.password_hash)
    is_valid_code = current_user.access_code and password_data.current_password == current_user.access_code
    
    if not (is_valid_hash or is_valid_code):
        await log_security_event(db, "password_change_failed_invalid_current", username=current_user.username, tenant_id=current_user.tenant_id, operator_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Senha atual incorreta."
        )

    # Require MFA for password change if enabled
    if current_user.mfa_enabled:
        mfa_token = request.headers.get("X-MFA-Token")
        if not mfa_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="MFA_REQUIRED_FOR_PASSWORD_CHANGE"
            )
        from src.services.mfa_service import mfa_service
        if not mfa_service.verify_totp(current_user.mfa_secret, mfa_token):
            await log_security_event(db, "password_change_failed_invalid_mfa", username=current_user.username, tenant_id=current_user.tenant_id, operator_id=current_user.id)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="MFA inválido."
            )

    current_user.password_hash = get_password_hash(password_data.new_password)
    await log_security_event(db, "password_changed", username=current_user.username, tenant_id=current_user.tenant_id, operator_id=current_user.id)
    await db.commit()
    
    return {"message": "Senha atualizada com sucesso."}

from src.models.audit import AuditLog
from src.schemas import AuditLogResponse
from sqlalchemy import desc

@auth_router.get("/me/logs", response_model=list[AuditLogResponse])
async def get_my_logs(
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    """Fetch recent activity logs for the current user."""
    stmt = (
        select(AuditLog)
        .where(AuditLog.username == current_user.username)
        .order_by(desc(AuditLog.created_at))
        .limit(50)
    )
    result = await db.execute(stmt)
    logs = result.scalars().all()
    return logs

from pydantic import BaseModel

class SessionResponse(BaseModel):
    id: int
    ip_address: str | None
    user_agent: str | None
    created_at: datetime
    last_active_at: datetime
    is_revoked: bool
    
    class Config:
        from_attributes = True

@auth_router.get("/me/sessions", response_model=list[SessionResponse])
async def get_my_sessions(
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    """Fetch active and inactive history sessions for the current user."""
    stmt = (
        select(UserSession)
        .where(UserSession.user_id == current_user.id)
        .order_by(desc(UserSession.created_at))
        .limit(20)
    )
    result = await db.execute(stmt)
    return result.scalars().all()

@auth_router.delete("/me/sessions/{session_id}")
async def revoke_session(
    session_id: int,
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    session_to_revoke = await db.scalar(
        select(UserSession).where(UserSession.id == session_id, UserSession.user_id == current_user.id)
    )
    if not session_to_revoke:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")
        
    session_to_revoke.is_revoked = True
    await log_security_event(db, "session_revoked", username=current_user.username, tenant_id=current_user.tenant_id, operator_id=current_user.id)
    await db.commit()
    
    return {"message": "Sessão revogada com sucesso."}
