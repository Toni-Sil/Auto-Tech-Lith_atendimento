"""
Master Admin Router — Cross-tenant global stats + internal financial view.

Access policy: caller must have role='owner' AND tenant_id IS NULL.
This represents the platform-level super-admin with no tenant affiliation.
"""

from datetime import datetime, timedelta
from typing import Annotated, List, Optional
import re

from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import get_db
from src.models.admin import AdminUser
from src.models.tenant import Tenant
from src.models.tenant_quota import TenantQuota
from src.models.agent_profile import AgentProfile
from src.models.audit import AuditLog
from src.api.auth import get_current_user
from src.services.usage_service import usage_service
from src.utils.security import get_password_hash
from src.utils.logger import setup_logger
from src.config import settings

logger = setup_logger(__name__)
master_router = APIRouter()


# ── Gate ─────────────────────────────────────────────────────────────────────

def _require_master_admin(current_user: AdminUser = Depends(get_current_user)) -> AdminUser:
    """
    Strict gate: only a platform-level owner, admin or master_admin with NO tenant affiliation
    may access these endpoints. Tenant owners are denied.
    """
    allowed_roles = ["owner", "admin", "master_admin", "master", "super admin", "superadmin"]
    user_role = (current_user.role or "").lower()
    if user_role not in allowed_roles or current_user.tenant_id is not None:
        logger.warning(f"⛔ Master Admin Access Denied: user={current_user.username}, role={user_role}, tenant_id={current_user.tenant_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Master Admin access required (role={user_role}, tenant_id={current_user.tenant_id}).",
        )
    return current_user


def _require_master_or_owner(current_user: AdminUser = Depends(get_current_user)) -> AdminUser:
    """
    Flexible gate: Allows platform admins OR tenant owners.
    Used for features that can be self-managed (like WhatsApp instances).
    """
    user_role = (current_user.role or "").lower()
    is_master = user_role in ["owner", "admin", "master_admin", "master", "super admin", "superadmin"] and current_user.tenant_id is None
    is_tenant_owner = user_role == "owner" and current_user.tenant_id is not None
    
    if not (is_master or is_tenant_owner):
        logger.warning(f"⛔ Access Denied: user={current_user.username}, role={user_role}, tenant_id={current_user.tenant_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Master Admin or Tenant Owner access required.",
        )
    return current_user


# ── Schemas ──────────────────────────────────────────────────────────────────

class TenantStatus(BaseModel):
    id: int
    name: str
    subdomain: Optional[str]
    is_active: bool
    created_at: Optional[str]
    interactions_30d: int
    tokens_30d: int
    cost_usd_30d: float
    tokens_30d: int
    cost_usd_30d: float
    last_active: Optional[str]

class TenantUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    is_active: Optional[bool] = None
    plan_tier: Optional[str] = None
    max_whatsapp_instances: Optional[int] = None
    max_messages_daily: Optional[int] = None
    max_messages_monthly: Optional[int] = None


class TenantAccountCreate(BaseModel):
    """
    Payload para o Master Admin criar uma nova conta (tenant + usuário owner).
    """

    tenant_name: str
    subdomain: str

    admin_name: str
    admin_email: str
    admin_phone: str
    admin_password: str

    # Configurações de plano / cotas (opcionais com defaults seguros)
    plan_tier: Optional[str] = "basic"
    max_whatsapp_instances: Optional[int] = 1
    max_messages_daily: Optional[int] = 1000
    max_messages_monthly: Optional[int] = 20000


class GlobalKPIResponse(BaseModel):
    total_tenants: int
    active_tenants: int
    total_interactions_30d: int
    total_tokens_30d: int
    total_cost_usd_30d: float
    churn_alert_count: int


class ChurnAlert(BaseModel):
    tenant_id: int
    last_week_interactions: int
    this_week_interactions: int
    drop_percent: float


class InternalAIConfig(BaseModel):
    base_prompt: str
    agent_name: Optional[str] = None
    tone: Optional[str] = None
    persona: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@master_router.get("/registrations")
async def get_registration_validations(
    master: Annotated[AdminUser, Depends(_require_master_admin)],
    db: AsyncSession = Depends(get_db),
):
    event_types = [
        "telegram_id_identified", 
        "telegram_access_code_validated",
        "customer_registered_by_agent",
        "login_success",
        "login_failure"
    ]
    
    stmt = (
        select(AuditLog)
        .where(AuditLog.event_type.in_(event_types))
        .order_by(desc(AuditLog.created_at))
        .limit(100)
    )
    
    rows = (await db.execute(stmt)).scalars().all()
    
    return [
        {
            "id": r.id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "event_type": r.event_type,
            "username": r.username,
            "details": r.details,
            "ip_address": r.ip_address
        }
        for r in rows
    ]

@master_router.get("/kpis", response_model=GlobalKPIResponse)
async def get_global_kpis(
    master: Annotated[AdminUser, Depends(_require_master_admin)],
    db: AsyncSession = Depends(get_db),
):
    """Platform-level KPI summary across all tenants."""
    total_stmt = select(func.count(Tenant.id))
    active_stmt = select(func.count(Tenant.id)).where(Tenant.is_active == True)
    total_tenants = await db.scalar(total_stmt) or 0
    active_tenants = await db.scalar(active_stmt) or 0

    from src.models.usage_log import UsageLog
    from_date = datetime.utcnow() - timedelta(days=30)
    usage_stmt = select(
        func.count(UsageLog.id).label("interactions"),
        func.sum(UsageLog.total_tokens).label("tokens"),
        func.sum(UsageLog.cost_usd).label("cost"),
    ).where(UsageLog.timestamp >= from_date)
    row = (await db.execute(usage_stmt)).one()

    churn = await usage_service.get_churn_candidates(db)

    return GlobalKPIResponse(
        total_tenants=total_tenants,
        active_tenants=active_tenants,
        total_interactions_30d=row.interactions or 0,
        total_tokens_30d=row.tokens or 0,
        total_cost_usd_30d=round(row.cost or 0, 4),
        churn_alert_count=len(churn),
    )


@master_router.get("/tenants", response_model=List[TenantStatus])
async def list_all_tenants(
    master: Annotated[AdminUser, Depends(_require_master_admin)],
    db: AsyncSession = Depends(get_db),
):
    """Full list of all tenants with their 30-day usage summary."""
    tenants = (await db.execute(select(Tenant))).scalars().all()
    ranking = {r["tenant_id"]: r for r in await usage_service.get_global_usage_ranking(db, limit=1000)}

    result = []
    for t in tenants:
        usage = ranking.get(t.id, {})
        result.append(
            TenantStatus(
                id=t.id,
                name=t.name,
                subdomain=t.subdomain,
                is_active=t.is_active,
                created_at=str(t.created_at) if t.created_at else None,
                interactions_30d=usage.get("interactions", 0),
                tokens_30d=usage.get("tokens", 0),
                cost_usd_30d=usage.get("cost_usd", 0.0),
                last_active=usage.get("last_active"),
            )
        )
    return result


@master_router.post("/tenants", status_code=status.HTTP_201_CREATED)
async def create_tenant_with_owner(
    body: TenantAccountCreate,
    master: Annotated[AdminUser, Depends(_require_master_admin)],
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import or_
    from src.models.audit import AuditLog
    import json

    if not re.match(r"^[a-z0-9-]+$", body.subdomain):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subdomínio inválido. Use apenas letras minúsculas, números e hífen.",
        )

    existing_tenant = await db.scalar(
        select(Tenant).where(Tenant.subdomain == body.subdomain)
    )
    if existing_tenant:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subdomínio já está em uso.",
        )

    existing_admin = await db.scalar(
        select(AdminUser).where(
            or_(
                AdminUser.username == body.admin_email,
                AdminUser.email == body.admin_email,
            )
        )
    )
    if existing_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="E-mail do usuário já está em uso.",
        )

    try:
        new_tenant = Tenant(
            name=body.tenant_name,
            subdomain=body.subdomain,
            status="active",
            is_active=True,
        )
        db.add(new_tenant)
        await db.flush()

        import secrets
        import string

        random_code = "".join(secrets.choice(string.digits) for _ in range(6))

        new_admin = AdminUser(
            tenant_id=new_tenant.id,
            username=body.admin_email,
            email=body.admin_email,
            name=body.admin_name,
            phone=body.admin_phone,
            password_hash=get_password_hash(body.admin_password),
            role="owner",
            access_code=random_code,
            email_verified=True,
            phone_verified=True,
            phone_otp=None,
        )
        db.add(new_admin)

        quota = TenantQuota(
            tenant_id=new_tenant.id,
            plan_tier=body.plan_tier or "basic",
            max_whatsapp_instances=body.max_whatsapp_instances or 1,
            max_messages_daily=body.max_messages_daily or 1000,
            max_messages_monthly=body.max_messages_monthly or 20000,
            updated_by=master.username,
        )
        db.add(quota)

        audit = AuditLog(
            tenant_id=new_tenant.id,
            event_type="tenant_created_by_master",
            username=master.username,
            details=json.dumps(
                {
                    "tenant": {
                        "name": new_tenant.name,
                        "subdomain": new_tenant.subdomain,
                        "plan_tier": quota.plan_tier,
                    },
                    "admin": {
                        "name": new_admin.name,
                        "email": new_admin.email,
                        "phone": new_admin.phone,
                    },
                }
            ),
        )
        db.add(audit)

        await db.commit()
        await db.refresh(new_tenant)
        await db.refresh(new_admin)

        return {
            "message": "Conta criada com sucesso.",
            "tenant_id": new_tenant.id,
            "admin_id": new_admin.id,
            "admin_email": new_admin.email,
        }

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha ao criar conta: {str(e)}",
        )


@master_router.get("/tenants/{tenant_id}")
async def get_tenant_details(
    tenant_id: int,
    master: Annotated[AdminUser, Depends(_require_master_admin)],
    db: AsyncSession = Depends(get_db),
):
    from src.models.tenant_quota import TenantQuota
    
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
        
    stmt = select(TenantQuota).where(TenantQuota.tenant_id == tenant_id)
    quota = (await db.execute(stmt)).scalars().first()
    
    return {
        "id": tenant.id,
        "name": tenant.name,
        "subdomain": tenant.subdomain,
        "status": tenant.status,
        "is_active": tenant.is_active,
        "plan_tier": quota.plan_tier if quota else "basic",
        "max_whatsapp_instances": quota.max_whatsapp_instances if quota else 1,
        "max_messages_daily": quota.max_messages_daily if quota else 1000,
        "max_messages_monthly": quota.max_messages_monthly if quota else 20000,
    }


@master_router.put("/tenants/{tenant_id}")
async def update_tenant(
    tenant_id: int,
    body: TenantUpdate,
    master: Annotated[AdminUser, Depends(_require_master_admin)],
    db: AsyncSession = Depends(get_db),
):
    from src.models.audit import AuditLog
    from src.models.tenant_quota import TenantQuota
    import json
    
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
        
    stmt = select(TenantQuota).where(TenantQuota.tenant_id == tenant_id)
    quota = (await db.execute(stmt)).scalars().first()
    
    old_data = {
        "name": tenant.name,
        "status": tenant.status,
        "is_active": tenant.is_active,
        "plan_tier": quota.plan_tier if quota else None,
        "max_whatsapp_instances": quota.max_whatsapp_instances if quota else None,
        "max_messages_daily": quota.max_messages_daily if quota else None,
        "max_messages_monthly": quota.max_messages_monthly if quota else None,
    }
    
    if body.name is not None:
        tenant.name = body.name
    if body.status is not None:
        tenant.status = body.status
    if body.is_active is not None:
        tenant.is_active = body.is_active
        
    from src.services.quota_service import quota_service
    quota = await quota_service.get_or_create(tenant_id, db)
    
    if body.plan_tier is not None:
        quota.plan_tier = body.plan_tier
    if body.max_whatsapp_instances is not None:
        quota.max_whatsapp_instances = body.max_whatsapp_instances
    if body.max_messages_daily is not None:
        quota.max_messages_daily = body.max_messages_daily
    if body.max_messages_monthly is not None:
        quota.max_messages_monthly = body.max_messages_monthly
    
    new_data = {
        "name": tenant.name,
        "status": tenant.status,
        "is_active": tenant.is_active,
        "plan_tier": quota.plan_tier,
        "max_whatsapp_instances": quota.max_whatsapp_instances,
        "max_messages_daily": quota.max_messages_daily,
        "max_messages_monthly": quota.max_messages_monthly,
    }
    
    if old_data != new_data:
        audit = AuditLog(
            tenant_id=tenant_id,
            event_type="tenant_updated_by_master",
            username=master.username,
            details=json.dumps({
                "old_data": old_data,
                "new_data": new_data
            })
        )
        db.add(audit)
        
    await db.commit()
    await db.refresh(tenant)
    await db.refresh(quota)
    return {"status": "success", "message": "Tenant atualizado com sucesso."}


@master_router.delete("/tenants/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant(
    tenant_id: int,
    master: Annotated[AdminUser, Depends(_require_master_admin)],
    db: AsyncSession = Depends(get_db),
):
    from src.models.audit import AuditLog
    import json

    logger.info(f"🗑️ Attempting to delete tenant ID: {tenant_id} (Master: {master.username})")
    
    tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    
    if not tenant:
        logger.warning(f"⚠️ Tenant {tenant_id} not found for deletion.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant não encontrado.")

    snapshot = {
        "id": tenant.id,
        "name": tenant.name,
        "subdomain": tenant.subdomain,
        "status": tenant.status,
        "is_active": tenant.is_active,
    }

    await db.delete(tenant)

    audit = AuditLog(
        tenant_id=tenant_id,
        event_type="tenant_deleted_by_master",
        username=master.username,
        details=json.dumps(snapshot),
    )
    db.add(audit)

    await db.commit()
    return None


@master_router.get("/usage/ranking")
async def get_usage_ranking(
    master: Annotated[AdminUser, Depends(_require_master_admin)],
    db: AsyncSession = Depends(get_db),
):
    return await usage_service.get_global_usage_ranking(db)


@master_router.get("/churn-alerts", response_model=List[ChurnAlert])
async def get_churn_alerts(
    master: Annotated[AdminUser, Depends(_require_master_admin)],
    db: AsyncSession = Depends(get_db),
    threshold: float = 0.5,
):
    alerts = await usage_service.get_churn_candidates(db, drop_threshold=threshold)
    return [ChurnAlert(**a) for a in alerts]


# ── Internal Financial Dashboard ──────────────────────────────────────────────

class TenantFinancialRow(BaseModel):
    tenant_id:   int
    tenant_name: str
    interactions_30d: int
    tokens_30d:       int
    cost_usd_30d:     float
    pct_of_total:     float


class FinancialSummary(BaseModel):
    total_cost_usd_30d:    float
    total_interactions_30d: int
    total_tokens_30d:       int
    avg_cost_per_tenant:    float
    estimated_cac_usd:      float
    breakdown:              List[TenantFinancialRow]


@master_router.get("/financial", response_model=FinancialSummary)
async def get_financial_dashboard(
    master: Annotated[AdminUser, Depends(_require_master_admin)],
    db: AsyncSession = Depends(get_db),
):
    from src.models.usage_log import UsageLog
    from src.models.tenant import Tenant

    from_date = datetime.utcnow() - timedelta(days=30)

    stmt = (
        select(
            UsageLog.tenant_id,
            func.count(UsageLog.id).label("interactions"),
            func.coalesce(func.sum(UsageLog.total_tokens), 0).label("tokens"),
            func.coalesce(func.sum(UsageLog.cost_usd), 0.0).label("cost"),
        )
        .where(UsageLog.timestamp >= from_date)
        .group_by(UsageLog.tenant_id)
        .order_by(desc(func.sum(UsageLog.cost_usd)))
    )
    rows = (await db.execute(stmt)).all()

    total_cost  = sum(r.cost for r in rows)
    total_inter = sum(r.interactions for r in rows)
    total_tok   = sum(r.tokens for r in rows)

    tenant_ids = [r.tenant_id for r in rows]
    tenants_q  = (await db.execute(select(Tenant).where(Tenant.id.in_(tenant_ids)))).scalars().all()
    t_names    = {t.id: t.name for t in tenants_q}

    breakdown = [
        TenantFinancialRow(
            tenant_id=r.tenant_id,
            tenant_name=t_names.get(r.tenant_id, f"Tenant #{r.tenant_id}"),
            interactions_30d=r.interactions,
            tokens_30d=r.tokens,
            cost_usd_30d=round(r.cost, 4),
            pct_of_total=round(r.cost / total_cost * 100, 1) if total_cost else 0.0,
        )
        for r in rows
    ]

    paying_count = len([r for r in rows if r.cost > 0])
    estimated_cac = round(total_cost / paying_count, 4) if paying_count else 0.0

    return FinancialSummary(
        total_cost_usd_30d=round(total_cost, 4),
        total_interactions_30d=total_inter,
        total_tokens_30d=total_tok,
        avg_cost_per_tenant=round(total_cost / max(len(rows), 1), 4),
        estimated_cac_usd=estimated_cac,
        breakdown=breakdown,
    )


@master_router.get("/financial/transactions")
async def get_transaction_history(
    master: Annotated[AdminUser, Depends(_require_master_admin)],
    db: AsyncSession = Depends(get_db),
    limit: int = 100,
):
    from src.models.usage_log import UsageLog
    stmt = (
        select(UsageLog)
        .order_by(desc(UsageLog.timestamp))
        .limit(min(limit, 500))
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id":          r.id,
            "tenant_id":   r.tenant_id,
            "event_type":  r.event_type,
            "model_used":  r.model_used,
            "provider":    r.provider,
            "input_tokens":  r.input_tokens,
            "output_tokens": r.output_tokens,
            "total_tokens":  r.total_tokens,
        }
        for r in rows
    ]

# ── Encrypted Vault (Cofre) ──────────────────────────────────────────────────

from src.schemas import VaultCredentialCreate, VaultCredentialResponse
from src.models.vault import VaultCredential
from src.utils.audit import log_security_event

def _get_fernet():
    try:
        from cryptography.fernet import Fernet
        import os
        key = os.environ.get("ENCRYPTION_KEY")
        if not key:
            raise RuntimeError("ENCRYPTION_KEY env variable is not set")
        return Fernet(key.encode() if isinstance(key, str) else key)
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="cryptography package not installed",
        )

def _mask_vault_key(encrypted_key: str) -> str:
    if not encrypted_key:
        return "not-set"
    tail = encrypted_key[-4:] if len(encrypted_key) >= 4 else "****"
    return f"****{tail}"

@master_router.get("/vault", response_model=List[VaultCredentialResponse])
async def list_vault_credentials(
    master: Annotated[AdminUser, Depends(_require_master_admin)],
    tenant_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(VaultCredential)
    if tenant_id:
        stmt = stmt.where(VaultCredential.tenant_id == tenant_id)
    credentials = (await db.execute(stmt)).scalars().all()
    
    return [
        VaultCredentialResponse(
            id=c.id,
            name=c.name,
            service_type=c.service_type,
            created_at=c.created_at
        ) for c in credentials
    ]

@master_router.post("/vault", response_model=VaultCredentialResponse)
async def create_vault_credential(
    body: VaultCredentialCreate,
    master: Annotated[AdminUser, Depends(_require_master_admin)],
    db: AsyncSession = Depends(get_db),
):
    fernet = _get_fernet()
    encrypted = fernet.encrypt(body.secret_value.encode()).decode()

    cred = VaultCredential(
        tenant_id=body.tenant_id,
        name=body.name,
        service_type=body.service_type,
        encrypted_value=encrypted
    )
    db.add(cred)
    await db.commit()
    await db.refresh(cred)

    await log_security_event(db, "vault_credential_created", username=master.username, operator_id=master.id, tenant_id=body.tenant_id)

    return VaultCredentialResponse(
        id=cred.id,
        name=cred.name,
        service_type=cred.service_type,
        created_at=cred.created_at
    )

@master_router.delete("/vault/{cred_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vault_credential(
    cred_id: int,
    master: Annotated[AdminUser, Depends(_require_master_admin)],
    db: AsyncSession = Depends(get_db),
):
    cred = await db.get(VaultCredential, cred_id)
    if not cred:
        raise HTTPException(status_code=404, detail="Credential not found")
        
    tenant_id = cred.tenant_id
    db.delete(cred)
    await db.commit()

    await log_security_event(db, "vault_credential_deleted", username=master.username, operator_id=master.id, tenant_id=tenant_id)


# ── Internal AI Config (Max) ────────────────────────────────────────────────

@master_router.get("/internal-ai/config", response_model=InternalAIConfig)
async def get_internal_ai_config(
    master: Annotated[AdminUser, Depends(_require_master_admin)],
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AgentProfile).where(
        AgentProfile.tenant_id == None, 
        AgentProfile.name == "internal-max"
    )
    config = (await db.execute(stmt)).scalars().first()
    
    if not config:
        return InternalAIConfig(
            agent_name="Max",
            tone="professional",
            persona="",
            base_prompt=""
        )
        
    return InternalAIConfig(
        agent_name=config.agent_name_display or "Max",
        tone=config.tone or "professional",
        persona=config.objective or "",
        base_prompt=config.base_prompt or ""
    )

@master_router.post("/internal-ai/config")
async def save_internal_ai_config(
    body: InternalAIConfig,
    master: Annotated[AdminUser, Depends(_require_master_admin)],
    db: AsyncSession = Depends(get_db),
):
    from src.models.audit import AuditLog
    from src.services.prompt_generator_service import prompt_generator_service
    import json
    
    # Auto-extract based on prompt if not explicitly given
    if body.base_prompt:
        extracted = await prompt_generator_service.analyze_prompt(body.base_prompt)
        body.agent_name = body.agent_name or extracted.get("name") or "Max"
        body.tone = body.tone or extracted.get("tone") or "neutro"
        body.persona = body.persona or extracted.get("objective") or "Assistente Interno"
    
    stmt = select(AgentProfile).where(
        AgentProfile.tenant_id == None, 
        AgentProfile.name == "internal-max"
    )
    config = (await db.execute(stmt)).scalars().first()
    
    if not config:
        config = AgentProfile(
            tenant_id=None,
            name="internal-max",
            agent_name_display=body.agent_name,
            tone=body.tone,
            objective=body.persona,
            base_prompt=body.base_prompt,
            is_active=True
        )
        db.add(config)
        await db.commit()
    else:
        old_prompt = config.base_prompt
        
        config.agent_name_display = body.agent_name
        config.tone = body.tone
        config.objective = body.persona
        config.base_prompt = body.base_prompt
        
        if old_prompt != body.base_prompt:
            audit = AuditLog(
                tenant_id=None,
                event_type="internal_agent_prompt_updated",
                username=master.username,
                details=json.dumps({
                    "old_prompt": old_prompt,
                    "new_prompt": body.base_prompt
                })
            )
            db.add(audit)
            
        await db.commit()
        
    return {"status": "success", "message": "Configuração salva com sucesso."}


# ── Account Configuration ────────────────────────────────────────────────────

class AccountProfileUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


class AccountPasswordChange(BaseModel):
    current_password: str
    new_password: str


@master_router.put("/account/profile")
async def update_account_profile(
    body: AccountProfileUpdate,
    master: Annotated[AdminUser, Depends(_require_master_admin)],
    db: AsyncSession = Depends(get_db),
):
    from src.models.audit import AuditLog
    import json

    old_data = {
        "name": master.name,
        "email": master.email,
    }

    if body.name is not None:
        master.name = body.name
    if body.email is not None:
        master.email = body.email
    if body.phone is not None:
        master.phone = body.phone if hasattr(master, 'phone') else None

    new_data = {
        "name": master.name,
        "email": master.email,
    }

    audit = AuditLog(
        tenant_id=None,
        event_type="master_profile_updated",
        username=master.username,
        details=json.dumps({"old": old_data, "new": new_data}),
    )
    db.add(audit)
    await db.commit()
    return {"status": "success", "message": "Perfil atualizado com sucesso."}


@master_router.put("/account/password")
async def change_account_password(
    body: AccountPasswordChange,
    master: Annotated[AdminUser, Depends(_require_master_admin)],
    db: AsyncSession = Depends(get_db),
):
    from src.models.audit import AuditLog
    import bcrypt

    current_hashed = master.hashed_password.encode() if isinstance(master.hashed_password, str) else master.hashed_password
    if not bcrypt.checkpw(body.current_password.encode(), current_hashed):
        await log_security_event(
            db, "master_password_change_failed",
            username=master.username,
            operator_id=master.id,
            metadata={"reason": "wrong_current_password"}
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Senha atual incorreta. Por favor, verifique e tente novamente."
        )

    if len(body.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A nova senha deve ter pelo menos 8 caracteres."
        )

    new_hashed = bcrypt.hashpw(body.new_password.encode(), bcrypt.gensalt()).decode()
    master.hashed_password = new_hashed

    audit = AuditLog(
        tenant_id=None,
        event_type="master_password_changed",
        username=master.username,
    )
    db.add(audit)
    await db.commit()

    await log_security_event(
        db, "master_password_change_success",
        username=master.username,
        operator_id=master.id
    )
    return {"status": "success", "message": "Senha alterada com sucesso."}


# ── WhatsApp / Evolution API Management ───────────────────────────────────────

from src.models.whatsapp import EvolutionInstance
from src.services.evolution_service import evolution_service

class WhatsAppInstanceCreate(BaseModel):
    tenant_id: Optional[int] = None
    instance_name: str
    display_name: Optional[str] = None
    instance_token: Optional[str] = None
    evolution_api_url: Optional[str] = None
    evolution_api_key: Optional[str] = None
    evolution_ip: Optional[str] = None
    owner_email: Optional[str] = None

class WhatsAppInstanceUpdate(BaseModel):
    display_name: Optional[str] = None
    instance_token: Optional[str] = None
    evolution_api_url: Optional[str] = None
    evolution_api_key: Optional[str] = None
    evolution_ip: Optional[str] = None
    owner_email: Optional[str] = None

class WhatsAppInstanceResponse(BaseModel):
    id: int
    tenant_id: Optional[int]
    tenant_name: Optional[str]
    display_name: Optional[str]
    instance_name: str
    phone_number: Optional[str]
    status: str
    created_at: Optional[str]
    webhook_url: Optional[str] = None
    evolution_api_url: Optional[str] = None
    evolution_api_key: Optional[str] = None
    evolution_ip: Optional[str] = None
    owner_email: Optional[str] = None

@master_router.get("/whatsapp", response_model=List[WhatsAppInstanceResponse])
async def list_whatsapp_instances(
    request: Request,
    master: Annotated[AdminUser, Depends(_require_master_admin)],
    db: AsyncSession = Depends(get_db),
):
    base_url = (settings.PUBLIC_URL or str(request.base_url)).rstrip("/")
    base_webhook_url = f"{base_url}{settings.API_V1_STR}/webhooks/whatsapp"
    
    try:
        stmt = select(EvolutionInstance, Tenant.name).outerjoin(Tenant, Tenant.id == EvolutionInstance.tenant_id)
        results = await db.execute(stmt)
        
        response = []
        for instance, tenant_name in results:
            response.append({
                "id": instance.id,
                "tenant_id": instance.tenant_id,
                "tenant_name": tenant_name or "Interno (Max)",
                "display_name": instance.display_name or instance.instance_name,
                "instance_name": instance.instance_name,
                "phone_number": instance.phone_number,
                "status": instance.status,
                "created_at": str(instance.created_at) if instance.created_at else None,
                "webhook_url": f"{base_webhook_url}?token={settings.VERIFY_TOKEN}",
                "evolution_api_url": instance.evolution_api_url,
                "evolution_api_key": instance.evolution_api_key,
                "evolution_ip": getattr(instance, "evolution_ip", None),
                "owner_email": getattr(instance, "owner_email", None),
            })
        return response
    except Exception as e:
        logger.error(f"Error listing WhatsApp instances: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao listar instâncias: {str(e)}")


@master_router.post("/whatsapp", status_code=status.HTTP_201_CREATED)
async def create_whatsapp_instance(
    request: Request,
    body: WhatsAppInstanceCreate,
    user: Annotated[AdminUser, Depends(_require_master_or_owner)],
    db: AsyncSession = Depends(get_db),
):
    """Create a new WhatsApp instance for a specific tenant in Evolution API and DB."""
    if user.tenant_id:
        body.tenant_id = user.tenant_id
        
    if body.tenant_id:
        tenant = await db.get(Tenant, body.tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found.")
        
    existing = await db.scalar(select(EvolutionInstance).where(EvolutionInstance.instance_name == body.instance_name))
    if existing:
        raise HTTPException(status_code=400, detail="Instance name already in use.")

    logger.info(f"Master Admin: Creating instance '{body.instance_name}' at {body.evolution_api_url or settings.EVOLUTION_API_URL}")

    new_instance = EvolutionInstance(
        tenant_id=body.tenant_id,
        instance_name=body.instance_name,
        display_name=body.display_name,
        instance_token=body.instance_token,
        evolution_api_url=body.evolution_api_url,
        evolution_api_key=body.evolution_api_key,
        evolution_ip=getattr(body, 'evolution_ip', None),
        owner_email=getattr(body, 'owner_email', None),
        status="pending"
    )
    db.add(new_instance)
    await db.commit()
    await db.refresh(new_instance)

    base_url = (settings.PUBLIC_URL or str(request.base_url)).rstrip("/")
    base_webhook_url = f"{base_url}{settings.API_V1_STR}/webhooks/whatsapp"
    webhook_url = f"{base_webhook_url}?token={settings.VERIFY_TOKEN}"

    evo_warning = None
    if body.evolution_api_url and body.evolution_api_key:
        try:
            evo_response = await evolution_service.create_instance(
                body.instance_name,
                token=body.instance_token,
                custom_url=body.evolution_api_url,
                custom_key=body.evolution_api_key
            )
            if "error" in evo_response:
                error_msg = str(evo_response.get("error", ""))
                status_code = evo_response.get("status_code")
                if status_code == 401:
                    evo_warning = "⚠️ Instância salva, mas a chave da Evolution API está incorreta (401). Verifique a API Key no servidor Evolution."
                elif status_code in [403, 409] and "already in use" in error_msg.lower():
                    evo_warning = f"⚠️ Instância salva no banco, mas o nome '{body.instance_name}' já existe na Evolution API."
                else:
                    evo_warning = f"⚠️ Instância salva no banco, mas houve erro na Evolution API: {error_msg[:120]}"
                logger.warning(f"Evolution API warning for '{body.instance_name}': {evo_response}")
            else:
                await evolution_service.set_settings(
                    new_instance.instance_name,
                    custom_url=body.evolution_api_url,
                    custom_key=body.evolution_api_key
                )
        except Exception as evo_exc:
            evo_warning = f"⚠️ Instância salva, mas não foi possível conectar à Evolution API: {str(evo_exc)[:100]}"
            logger.error(f"Evolution API exception for '{body.instance_name}': {evo_exc}")
    else:
        evo_warning = "ℹ️ Instância salva sem registro na Evolution API (URL/Key não informados)."

    return {
        "status": "success",
        "instance_id": new_instance.id,
        "instance_name": new_instance.instance_name,
        "webhook_url": webhook_url,
        "warning": evo_warning,
        "message": evo_warning or "Instância criada e configurada com sucesso!"
    }

@master_router.put("/whatsapp/{instance_name}", response_model=WhatsAppInstanceResponse)
async def update_whatsapp_instance(
    instance_name: str,
    body: WhatsAppInstanceUpdate,
    request: Request,
    master: Annotated[AdminUser, Depends(_require_master_admin)],
    db: AsyncSession = Depends(get_db),
):
    """Edit an existing WhatsApp instance's details."""
    instance = await db.scalar(select(EvolutionInstance).where(EvolutionInstance.instance_name == instance_name))
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found.")

    # ── Validar credenciais ANTES de salvar, se URL ou Key foram alteradas ────
    new_url = body.evolution_api_url if body.evolution_api_url is not None else instance.evolution_api_url
    new_key = body.evolution_api_key if body.evolution_api_key is not None else instance.evolution_api_key
    credentials_changed = (
        body.evolution_api_url is not None or body.evolution_api_key is not None
    )

    if credentials_changed and new_url and new_key:
        try:
            check = await evolution_service.check_instance_status(
                instance_name=instance_name,
            )
            # Faz chamada direta com as novas credenciais para validar
            import httpx
            test_url = f"{new_url.rstrip('/')}/instance/connectionState/{instance_name}"
            async with httpx.AsyncClient() as client:
                test_resp = await client.get(
                    test_url,
                    headers={"apikey": new_key, "Content-Type": "application/json"},
                    timeout=8.0
                )
                if test_resp.status_code == 401:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="⚠️ Credenciais inválidas (401). Verifique a URL e a API Key da Evolution antes de salvar."
                    )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Could not validate Evolution credentials on update for '{instance_name}': {e}")
            # Não bloquear se não conseguir checar (ex: instância offline) — apenas logar

    if body.display_name is not None:
        instance.display_name = body.display_name
    if body.instance_token is not None:
        instance.instance_token = body.instance_token
    if body.evolution_api_url is not None:
        instance.evolution_api_url = body.evolution_api_url
    if body.evolution_api_key is not None:
        instance.evolution_api_key = body.evolution_api_key
    if body.evolution_ip is not None:
        instance.evolution_ip = body.evolution_ip
    if body.owner_email is not None:
        instance.owner_email = body.owner_email

    await db.commit()
    await db.refresh(instance)

    base_url = (settings.PUBLIC_URL or str(request.base_url)).rstrip("/")
    base_webhook_url = f"{base_url}{settings.API_V1_STR}/webhooks/whatsapp"
    webhook_url = f"{base_webhook_url}?token={settings.VERIFY_TOKEN}"

    try:
        await evolution_service.set_settings(
            instance.instance_name,
            custom_url=instance.evolution_api_url,
            custom_key=instance.evolution_api_key
        )
    except Exception as e:
        logger.warning(f"Failed to re-sync Evolution API after update for {instance_name}: {e}")

    tenant_name = await db.scalar(select(Tenant.name).where(Tenant.id == instance.tenant_id)) if instance.tenant_id else "Interno (Max)"
    
    return {
        "id": instance.id,
        "tenant_id": instance.tenant_id,
        "tenant_name": tenant_name,
        "display_name": instance.display_name,
        "instance_name": instance.instance_name,
        "phone_number": instance.phone_number,
        "status": instance.status,
        "created_at": str(instance.created_at) if instance.created_at else None,
        "webhook_url": webhook_url,
        "evolution_api_url": instance.evolution_api_url,
        "evolution_api_key": instance.evolution_api_key
    }

@master_router.get("/whatsapp/{instance_name}/diagnose")
async def diagnose_whatsapp_instance(
    instance_name: str,
    master: Annotated[AdminUser, Depends(_require_master_admin)],
    db: AsyncSession = Depends(get_db),
):
    """Diagnóstico completo da instância: testa credenciais, estado e webhook."""
    import httpx

    instance = await db.scalar(select(EvolutionInstance).where(EvolutionInstance.instance_name == instance_name))
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found.")

    result = {
        "instance_name": instance_name,
        "db_status": instance.status,
        "evolution_reachable": False,
        "evolution_state": None,
        "credentials_valid": False,
        "webhook_configured": False,
        "webhook_url_registered": None,
        "errors": []
    }

    url = instance.evolution_api_url
    key = instance.evolution_api_key

    if not url or not key:
        result["errors"].append("URL ou API Key da Evolution não configuradas nesta instância.")
        return result

    # 1. Testar credenciais e estado da instância
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{url.rstrip('/')}/instance/connectionState/{instance_name}",
                headers={"apikey": key},
                timeout=8.0
            )
            if resp.status_code == 401:
                result["errors"].append("Credenciais inválidas (401). Verifique a API Key.")
            elif resp.status_code == 404:
                result["evolution_reachable"] = True
                result["credentials_valid"] = True
                result["errors"].append("Instância não encontrada na Evolution API. Pode precisar ser recriada.")
            elif resp.status_code == 200:
                result["evolution_reachable"] = True
                result["credentials_valid"] = True
                data = resp.json()
                state = data.get("instance", {}).get("state") or data.get("state")
                result["evolution_state"] = state  # "open", "close", "connecting", etc.
            else:
                result["evolution_reachable"] = True
                result["errors"].append(f"Resposta inesperada da Evolution: HTTP {resp.status_code}")
    except httpx.ConnectError:
        result["errors"].append(f"Não foi possível conectar à Evolution API em: {url}")
    except Exception as e:
        result["errors"].append(f"Erro ao contatar Evolution API: {str(e)[:100]}")

    # 2. Verificar webhook configurado na instância
    if result["credentials_valid"]:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{url.rstrip('/')}/webhook/find/{instance_name}",
                    headers={"apikey": key},
                    timeout=8.0
                )
                if resp.status_code == 200:
                    wh_data = resp.json()
                    wh_url = wh_data.get("url") or wh_data.get("webhook", {}).get("url")
                    result["webhook_url_registered"] = wh_url
                    result["webhook_configured"] = bool(wh_url)
                    if not wh_url:
                        result["errors"].append("Webhook não configurado na Evolution para esta instância.")
        except Exception as e:
            result["errors"].append(f"Não foi possível verificar webhook: {str(e)[:80]}")

    return result

@master_router.get("/whatsapp/{instance_name}/pairing-code")
async def get_pairing_code(
    instance_name: str,
    phone: str,
    user: Annotated[AdminUser, Depends(_require_master_or_owner)],
    db: AsyncSession = Depends(get_db),
):
    clean_phone = re.sub(r"\D", "", phone)
    if not clean_phone:
        raise HTTPException(status_code=400, detail="Invalid phone number format.")
        
    instance = await db.scalar(select(EvolutionInstance).where(EvolutionInstance.instance_name == instance_name))
    if not instance:
         raise HTTPException(status_code=404, detail="Instance not found.")
         
    if user.tenant_id and instance.tenant_id != user.tenant_id:
        raise HTTPException(status_code=403, detail="Forbidden: This instance belongs to another tenant.")

    custom_url = instance.evolution_api_url
    custom_key = instance.evolution_api_key

    evo_response = await evolution_service.get_pairing_code(
        instance_name, 
        clean_phone,
        custom_url=custom_url,
        custom_key=custom_key
    )
    if "error" in evo_response:
        raise HTTPException(status_code=500, detail=f"Evolution API Error: {evo_response['error']}")
        
    return evo_response

@master_router.delete("/whatsapp/{instance_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_whatsapp_instance(
    instance_name: str,
    master: Annotated[AdminUser, Depends(_require_master_admin)],
    db: AsyncSession = Depends(get_db),
):
    instance = await db.scalar(select(EvolutionInstance).where(EvolutionInstance.instance_name == instance_name))
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found in database.")
        
    evo_response = await evolution_service.delete_instance(
        instance_name,
        custom_url=instance.evolution_api_url,
        custom_key=instance.evolution_api_key
    )
    if "error" in evo_response:
        logger.warning(f"Evolution API Error on delete: {evo_response['error']} - Proceeding with DB cleanup.")
         
    await db.delete(instance)
    await db.commit()
    return None


# ── System Config (Configurações do Sistema) ─────────────────────────────────

class SystemConfigResponse(BaseModel):
    openai_api_key: str
    openai_model: str
    evolution_api_url: str
    evolution_api_key: str
    verify_token: str
    access_token_expire_minutes: int
    refresh_token_expire_minutes: int
    smtp_server: str
    smtp_port: int
    smtp_user: str
    backend_cors_origins: str
    app_debug: bool
    public_url: str
    rate_limit_whitelist: str


class SystemConfigUpdate(BaseModel):
    openai_api_key: Optional[str] = None
    openai_model: Optional[str] = None
    evolution_api_url: Optional[str] = None
    evolution_api_key: Optional[str] = None
    verify_token: Optional[str] = None
    access_token_expire_minutes: Optional[int] = None
    refresh_token_expire_minutes: Optional[int] = None
    smtp_server: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    backend_cors_origins: Optional[str] = None
    app_debug: Optional[bool] = None
    public_url: Optional[str] = None
    rate_limit_whitelist: Optional[str] = None


def _mask(value: str, show_last: int = 4) -> str:
    """Mascarar credencial sensível, exibindo apenas os últimos N caracteres."""
    if not value:
        return ""
    if len(value) <= show_last:
        return "****"
    return "****" + value[-show_last:]


@master_router.get("/system-config", response_model=SystemConfigResponse)
async def get_system_config(
    master: Annotated[AdminUser, Depends(_require_master_admin)],
):
    """Retorna as configurações atuais do sistema (campos sensíveis são mascarados)."""
    return SystemConfigResponse(
        openai_api_key=_mask(getattr(settings, "OPENAI_API_KEY", "") or ""),
        openai_model=getattr(settings, "OPENAI_MODEL", "gpt-4o-mini") or "gpt-4o-mini",
        evolution_api_url=getattr(settings, "EVOLUTION_API_URL", "") or "",
        evolution_api_key=_mask(getattr(settings, "EVOLUTION_API_KEY", "") or ""),
        verify_token=_mask(getattr(settings, "VERIFY_TOKEN", "") or ""),
        access_token_expire_minutes=getattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES", 30),
        refresh_token_expire_minutes=getattr(settings, "REFRESH_TOKEN_EXPIRE_MINUTES", 1440),
        smtp_server=getattr(settings, "SMTP_SERVER", "") or "",
        smtp_port=getattr(settings, "SMTP_PORT", 587),
        smtp_user=getattr(settings, "SMTP_USER", "") or "",
        backend_cors_origins=str(getattr(settings, "BACKEND_CORS_ORIGINS", "*")),
        app_debug=getattr(settings, "APP_DEBUG", False),
        public_url=getattr(settings, "PUBLIC_URL", "") or "",
        rate_limit_whitelist=getattr(settings, "RATE_LIMIT_WHITELIST", "127.0.0.1") or "127.0.0.1",
    )


@master_router.post("/system-config")
async def update_system_config(
    body: SystemConfigUpdate,
    master: Annotated[AdminUser, Depends(_require_master_admin)],
    db: AsyncSession = Depends(get_db),
):
    """
    Atualiza configurações do sistema em runtime.
    ⚠️ As mudanças são aplicadas em memória — reinicie o container para persistir no .env.
    """
    import json
    changed = {}

    field_map = {
        "openai_api_key": "OPENAI_API_KEY",
        "openai_model": "OPENAI_MODEL",
        "evolution_api_url": "EVOLUTION_API_URL",
        "evolution_api_key": "EVOLUTION_API_KEY",
        "verify_token": "VERIFY_TOKEN",
        "access_token_expire_minutes": "ACCESS_TOKEN_EXPIRE_MINUTES",
        "refresh_token_expire_minutes": "REFRESH_TOKEN_EXPIRE_MINUTES",
        "smtp_server": "SMTP_SERVER",
        "smtp_port": "SMTP_PORT",
        "smtp_user": "SMTP_USER",
        "smtp_password": "SMTP_PASSWORD",
        "backend_cors_origins": "BACKEND_CORS_ORIGINS",
        "app_debug": "APP_DEBUG",
        "public_url": "PUBLIC_URL",
        "rate_limit_whitelist": "RATE_LIMIT_WHITELIST",
    }

    for body_field, settings_attr in field_map.items():
        value = getattr(body, body_field, None)
        if value is not None:
            old_val = getattr(settings, settings_attr, None)
            setattr(settings, settings_attr, value)
            # Não logar valores sensíveis
            safe_val = _mask(str(value)) if "key" in body_field or "password" in body_field or "token" in body_field else str(value)
            changed[settings_attr] = safe_val

    if changed:
        audit = AuditLog(
            tenant_id=None,
            event_type="system_config_updated",
            username=master.username,
            details=json.dumps({"changed_fields": list(changed.keys()), "values": changed}),
        )
        db.add(audit)
        await db.commit()

        logger.info(f"⚙️ System config updated by {master.username}: {list(changed.keys())}")

    return {
        "status": "success",
        "message": "Configurações aplicadas em runtime. Reinicie o container para persistir no .env.",
        "changed_fields": list(changed.keys()),
    }
