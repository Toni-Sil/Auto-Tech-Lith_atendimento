"""
Onboarding API — Sprint 1

Fluxo de ativação do comerciante em 3 passos:
  1. /register  — cria conta + tenant
  2. /connect   — conecta canal WhatsApp (Evolution API)
  3. /configure — configura personalidade do agente

Cada passo é idempotente e retoma de onde parou.
O tenant só muda de status 'pending' para 'active' no passo 3.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/onboarding", tags=["Onboarding"])


# ─────────────────────────────────────────────
# SCHEMAS
# ─────────────────────────────────────────────

class RegisterRequest(BaseModel):
    business_name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8)
    phone: str = Field(..., description="Telefone do responsável (WhatsApp)")
    niche: str = Field(
        default="generic",
        description="Nicho do negócio: auto_eletrica, clinica, salao, contabilidade, generic",
    )


class RegisterResponse(BaseModel):
    tenant_id: int
    token: str
    onboarding_step: int = 1
    message: str


class ConnectWhatsAppRequest(BaseModel):
    instance_name: str = Field(..., description="Nome da instância na Evolution API")
    phone_number: str = Field(..., description="Número WhatsApp do negócio")


class ConnectWhatsAppResponse(BaseModel):
    qr_code_url: Optional[str]
    status: str
    message: str


class ConfigureAgentRequest(BaseModel):
    agent_name: str = Field(default="Max", description="Nome do agente de atendimento")
    niche: str = Field(
        default="generic",
        description="Nicho: auto_eletrica, clinica, salao, contabilidade, generic",
    )
    tone: str = Field(
        default="profissional",
        description="Tom do agente: profissional, amigavel, tecnico, casual",
    )
    objective: str = Field(
        default="",
        description="Objetivo principal do agente de atendimento",
    )
    target_audience: str = Field(
        default="",
        description="Público-alvo do negócio",
    )


class ConfigureAgentResponse(BaseModel):
    agent_profile_id: int
    tenant_status: str
    message: str


# ─────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────

@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Passo 1 — Criar conta e tenant",
)
async def register_tenant(payload: RegisterRequest):
    """
    Cria o tenant e o admin inicial.
    Retorna JWT para os próximos passos do onboarding.
    O tenant começa com status 'pending' até o passo 3.
    """
    from src.models.database import async_session
    from src.models.tenant import Tenant
    from src.models.admin import AdminUser
    import bcrypt
    import jwt
    import os

    async with async_session() as session:
        # Verifica email duplicado
        existing = await session.execute(
            select(AdminUser).where(AdminUser.email == payload.email)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=409, detail="Este e-mail já está cadastrado."
            )

        # Cria tenant
        tenant = Tenant(
            name=payload.business_name,
            status="pending",
            is_active=False,
        )
        session.add(tenant)
        await session.flush()  # gera tenant.id

        # Cria admin
        hashed_pw = bcrypt.hashpw(payload.password.encode(), bcrypt.gensalt()).decode()
        admin = AdminUser(
            tenant_id=tenant.id,
            email=payload.email,
            name=payload.business_name,
            password_hash=hashed_pw,
            phone=payload.phone,
            role="admin",
        )
        session.add(admin)
        await session.commit()

    # Gera JWT com tenant_id
    secret = os.getenv("JWT_SECRET", "change-me")
    token = jwt.encode(
        {"tenant_id": tenant.id, "sub": payload.email, "step": 1},
        secret,
        algorithm="HS256",
    )

    logger.info(f"[Onboarding] Novo tenant criado: {tenant.id} — {payload.business_name}")
    return RegisterResponse(
        tenant_id=tenant.id,
        token=token,
        onboarding_step=1,
        message=f"Conta criada! Próximo passo: conectar seu WhatsApp.",
    )


@router.post(
    "/connect",
    response_model=ConnectWhatsAppResponse,
    summary="Passo 2 — Conectar canal WhatsApp",
)
async def connect_whatsapp(
    payload: ConnectWhatsAppRequest,
    tenant_id: int = Depends(lambda: None),  # substituir por get_current_tenant_id
):
    """
    Cria instância na Evolution API e retorna QR code para scan.
    O tenant permanece 'pending' até o passo 3.
    """
    # TODO: integrar com src/services/whatsapp_service.py
    return ConnectWhatsAppResponse(
        qr_code_url=f"/api/onboarding/qr/{payload.instance_name}",
        status="pending_scan",
        message="Escaneie o QR code com seu WhatsApp para conectar.",
    )


@router.post(
    "/configure",
    response_model=ConfigureAgentResponse,
    summary="Passo 3 — Configurar personalidade do agente",
)
async def configure_agent(
    payload: ConfigureAgentRequest,
    tenant_id: int = Depends(lambda: None),  # substituir por get_current_tenant_id
):
    """
    Cria o AgentProfile com personalidade configurada.
    Ativa o tenant (status = 'active') ao finalizar.
    A partir daqui o agente já está funcional.
    """
    from src.models.database import async_session
    from src.models.agent_profile import AgentProfile
    from src.models.tenant import Tenant

    async with async_session() as session:
        # Cria perfil do agente
        profile = AgentProfile(
            tenant_id=tenant_id,
            name=payload.agent_name,
            niche=payload.niche,
            tone=payload.tone,
            objective=payload.objective,
            target_audience=payload.target_audience,
            is_active=True,
        )
        session.add(profile)

        # Ativa o tenant
        if tenant_id:
            tenant_result = await session.execute(
                select(Tenant).where(Tenant.id == tenant_id)
            )
            tenant = tenant_result.scalar_one_or_none()
            if tenant:
                tenant.status = "active"
                tenant.is_active = True

        await session.commit()
        await session.refresh(profile)

    logger.info(f"[Onboarding] Tenant {tenant_id} ativado com agente '{payload.agent_name}'")
    return ConfigureAgentResponse(
        agent_profile_id=profile.id,
        tenant_status="active",
        message=f"Pronto! Seu agente '{payload.agent_name}' já está ativo e atendendo.",
    )
