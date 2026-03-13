from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import get_current_user
from src.models.admin import AdminUser
from src.models.database import get_db
from src.services.mfa_service import mfa_service
from src.utils.audit import log_security_event
from src.utils.logger import setup_logger

logger = setup_logger(__name__)
mfa_router = APIRouter()


class MFASetupResponse(BaseModel):
    secret: str
    qr_code_base64: str


class MFAVerifyRequest(BaseModel):
    code: str


@mfa_router.post("/setup", response_model=MFASetupResponse)
async def setup_mfa(
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a new MFA secret, provisioning URI, and QR Code.
    Does NOT enable MFA yet; requires calling /verify to confirm.
    """
    if current_user.mfa_enabled:
        raise HTTPException(status_code=400, detail="MFA implies is already enabled.")

    secret = mfa_service.generate_secret()
    # Save the secret temporarily. We shouldn't enable it yet.
    current_user.mfa_secret = secret
    await db.commit()

    uri = mfa_service.get_provisioning_uri(
        secret=secret, username=current_user.username
    )
    qr_base64 = mfa_service.generate_qr_code_base64(uri)

    # Ideally, we return the secret and QR code, but do not set mfa_enabled=True until verified.
    return MFASetupResponse(secret=secret, qr_code_base64=qr_base64)


@mfa_router.post("/verify")
async def verify_mfa_setup(
    request: Request,
    data: MFAVerifyRequest,
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """
    Verify the first TOTP code and enable MFA permanently for the user.
    """
    if current_user.mfa_enabled:
        return {"status": "MFA is already enabled"}

    if not current_user.mfa_secret:
        raise HTTPException(status_code=400, detail="Please call /setup first.")

    is_valid = mfa_service.verify_totp(current_user.mfa_secret, data.code)
    if not is_valid:
        await log_security_event(
            db,
            "mfa_setup_failed",
            username=current_user.username,
            ip_address=request.client.host,
        )
        raise HTTPException(status_code=400, detail="Invalid MFA code. Try again.")

    current_user.mfa_enabled = True
    await log_security_event(
        db,
        "mfa_enabled",
        username=current_user.username,
        ip_address=request.client.host,
    )
    await db.commit()

    return {"status": "success", "message": "MFA activated successfully."}


@mfa_router.post("/disable")
async def disable_mfa(
    request: Request,
    data: MFAVerifyRequest,
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """
    Disable MFA. Requires a valid TOTP code.
    """
    if not current_user.mfa_enabled:
        raise HTTPException(status_code=400, detail="MFA is not enabled.")

    is_valid = mfa_service.verify_totp(current_user.mfa_secret, data.code)
    if not is_valid:
        await log_security_event(
            db,
            "mfa_disable_failed",
            username=current_user.username,
            ip_address=request.client.host,
        )
        raise HTTPException(status_code=400, detail="Invalid MFA code.")

    current_user.mfa_enabled = False
    current_user.mfa_secret = None

    await log_security_event(
        db,
        "mfa_disabled",
        username=current_user.username,
        ip_address=request.client.host,
    )
    await db.commit()

    return {"status": "success", "message": "MFA disabled."}
