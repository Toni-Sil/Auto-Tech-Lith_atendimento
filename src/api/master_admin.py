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
    if current_user.role not in ["owner", "admin", "master_admin"] or current_user.tenant_id is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Master Admin access required. This endpoint is restricted to platform-level administrators.",
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
    agent_name: str
    tone: str
    persona: Optional[str]
    base_prompt: Optional[str]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@master_router.get("/registrations")
async def get_registration_validations(
    master: Annotated[AdminUser, Depends(_require_master_admin)],
    db: AsyncSession = Depends(get_db),
):
    """
    Lista os logs de auditoria relacionados à validação de registros e acesso.
    Mostra como o agente identifica e valida cada pessoa (Admin ou Lead).
    """
    # Eventos de interesse
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
    # Count tenants
    total_stmt = select(func.count(Tenant.id))
    active_stmt = select(func.count(Tenant.id)).where(Tenant.is_active == True)
    total_tenants = await db.scalar(total_stmt) or 0
    active_tenants = await db.scalar(active_stmt) or 0

    # Usage aggregation (all tenants combined)
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
    """
    Cria uma nova conta completa:
    - Novo tenant
    - Usuário owner associado
    - Registro de cotas básicas
    """
    from sqlalchemy import or_
    from src.models.audit import AuditLog
    import json

    # Validação básica de subdomínio (mesma regra do /tenant/register público)
    if not re.match(r"^[a-z0-9-]+$", body.subdomain):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subdomínio inválido. Use apenas letras minúsculas, números e hífen.",
        )

    # Garante unicidade de subdomínio
    existing_tenant = await db.scalar(
        select(Tenant).where(Tenant.subdomain == body.subdomain)
    )
    if existing_tenant:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subdomínio já está em uso.",
        )

    # Garante que o e-mail/username do admin não está sendo reutilizado
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
        # 1) Cria o Tenant já ativo
        new_tenant = Tenant(
            name=body.tenant_name,
            subdomain=body.subdomain,
            status="active",
            is_active=True,
        )
        db.add(new_tenant)
        await db.flush()  # garante new_tenant.id

        # 2) Cria o usuário owner principal dessa conta
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
            # Criado manualmente pelo Master → consideramos verificado
            email_verified=True,
            phone_verified=True,
            phone_otp=None,
        )
        db.add(new_admin)

        # 3) Define cotas iniciais para o tenant
        quota = TenantQuota(
            tenant_id=new_tenant.id,
            plan_tier=body.plan_tier or "basic",
            max_whatsapp_instances=body.max_whatsapp_instances or 1,
            max_messages_daily=body.max_messages_daily or 1000,
            max_messages_monthly=body.max_messages_monthly or 20000,
            updated_by=master.username,
        )
        db.add(quota)

        # 4) Audit log da criação
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
    """Get detailed information about a specific tenant, including quotas."""
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
    """Update general details and limits (quotas) of a tenant."""
    from src.models.audit import AuditLog
    from src.models.tenant_quota import TenantQuota
    import json
    
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
        
    stmt = select(TenantQuota).where(TenantQuota.tenant_id == tenant_id)
    quota = (await db.execute(stmt)).scalars().first()
    
    # Store old values for audit logging
    old_data = {
        "name": tenant.name,
        "status": tenant.status,
        "is_active": tenant.is_active,
        "plan_tier": quota.plan_tier if quota else None,
        "max_whatsapp_instances": quota.max_whatsapp_instances if quota else None,
        "max_messages_daily": quota.max_messages_daily if quota else None,
        "max_messages_monthly": quota.max_messages_monthly if quota else None,
    }
    
    # Update Tenant
    if body.name is not None:
        tenant.name = body.name
    if body.status is not None:
        tenant.status = body.status
    if body.is_active is not None:
        tenant.is_active = body.is_active
        
    # Update Quota (ensure it exists)
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
    
    # Create audit log
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
    """
    Exclusão definitiva de um tenant e seus dados associados.

    Uso recomendado apenas para ambientes de teste ou contas claramente descartáveis.
    """
    from src.models.audit import AuditLog
    import json

    logger.info(f"🗑️ Attempting to delete tenant ID: {tenant_id} (Master: {master.username})")
    
    # Use explicit select to avoid potential issues with db.get in some edge cases
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

    # Remoção via ORM para respeitar cascades definidos nos relacionamentos
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
    """Top tenants by token consumption in the last 30 days."""
    return await usage_service.get_global_usage_ranking(db)


@master_router.get("/churn-alerts", response_model=List[ChurnAlert])
async def get_churn_alerts(
    master: Annotated[AdminUser, Depends(_require_master_admin)],
    db: AsyncSession = Depends(get_db),
    threshold: float = 0.5,
):
    """
    Returns tenants with a week-over-week usage drop >= threshold (default 50%).
    Use for proactive churn prevention.
    """
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
    estimated_cac_usd:      float   # total_cost / number_of_paying_tenants
    breakdown:              List[TenantFinancialRow]


@master_router.get("/financial", response_model=FinancialSummary)
async def get_financial_dashboard(
    master: Annotated[AdminUser, Depends(_require_master_admin)],
    db: AsyncSession = Depends(get_db),
):
    """Internal cost rateio and CAC dashboard for the last 30 days."""
    from src.models.usage_log import UsageLog
    from src.models.tenant import Tenant

    from_date = datetime.utcnow() - timedelta(days=30)

    # Per-tenant aggregation
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

    # Fetch tenant names in one shot
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
    """Last N usage log entries across all tenants (token consumption history)."""
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
    """Fetch the configuration of the internal agent (Max)."""
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
    """Save/Update the configuration of the internal agent (Max)."""
    from src.models.audit import AuditLog
    import json
    
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
        # Save old config context for audit
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
    """Update the Master Admin's profile information (name, email, phone)."""
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
    """Change the Master Admin's password. Requires current password verification."""
    from src.models.audit import AuditLog
    import bcrypt

    # Verify current password
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

    # Validate new password length
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
    master: Annotated[AdminUser, Depends(_require_master_admin)],
    db: AsyncSession = Depends(get_db),
):
    """Create a new WhatsApp instance for a specific tenant in Evolution API and DB."""
    # Check if tenant exists (only if tenant_id is provided)
    if body.tenant_id:
        tenant = await db.get(Tenant, body.tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found.")
        
    # Check if instance name is already taken in DB
    existing = await db.scalar(select(EvolutionInstance).where(EvolutionInstance.instance_name == body.instance_name))
    if existing:
        raise HTTPException(status_code=400, detail="Instance name already in use.")

    logger.info(f"Master Admin: Creating instance '{body.instance_name}' at {body.evolution_api_url or settings.EVOLUTION_API_URL}")
    
    # Create in Evolution API
    # Pass custom token if provided
    evo_response = await evolution_service.create_instance(
        body.instance_name, 
        token=body.instance_token,
        custom_url=body.evolution_api_url,
        custom_key=body.evolution_api_key
    )
    if "error" in evo_response:
        error_msg = evo_response.get("error", "")
        # Check for Evolution API "already in use" error
        if evo_response.get("status_code") in [403, 409] and "already in use" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=f"O nome '{body.instance_name}' já está em uso na Evolution API. Escolha outro nome ou remova a instância antiga."
            )
        
        # Check for 401 Unauthorized
        if evo_response.get("status_code") == 401:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Chave Global (API Key) da Evolution API está incorreta ou não autorizada. Verifique as configurações."
            )

        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Evolution API Error: {evo_response}")
        
    # Save to DB
    new_instance = EvolutionInstance(
        tenant_id=body.tenant_id,
        instance_name=body.instance_name,
        display_name=body.display_name,
        instance_token=body.instance_token,
        evolution_api_url=body.evolution_api_url,
        evolution_api_key=body.evolution_api_key,
        evolution_ip=body.evolution_ip,
        owner_email=body.owner_email,
        status="pending"
    )
    db.add(new_instance)
    await db.commit()
    await db.refresh(new_instance)
    
    base_url = (settings.PUBLIC_URL or str(request.base_url)).rstrip("/")
    base_webhook_url = f"{base_url}{settings.API_V1_STR}/webhooks/whatsapp"
    webhook_url = f"{base_webhook_url}?token={settings.VERIFY_TOKEN}"
    
    # --- AUTOMATIC CONFIGURATION ---
    # 1. Set Optimal Settings
    await evolution_service.set_settings(
        new_instance.instance_name,
        custom_url=body.evolution_api_url,
        custom_key=body.evolution_api_key
    )
    
    return {
        "status": "success", 
        "instance_id": new_instance.id, 
        "instance_name": new_instance.instance_name,
        "webhook_url": webhook_url,
        "message": "Instância criada e configurada (Settings aplicados. Webhook deve ser Global)."
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

    # Re-apply settings to ensure changes propagate to Evolution API
    base_url = (settings.PUBLIC_URL or str(request.base_url)).rstrip("/")
    base_webhook_url = f"{base_url}{settings.API_V1_STR}/webhooks/whatsapp"
    webhook_url = f"{base_webhook_url}?token={settings.VERIFY_TOKEN}"

    # Ignore errors during these background updates since the main edit is DB level
    try:
        await evolution_service.set_settings(
            instance.instance_name,
            custom_url=instance.evolution_api_url,
            custom_key=instance.evolution_api_key
        )
    except Exception as e:
        logger.warning(f"Failed to re-sync Evolution API after update for {instance_name}: {e}")

    # For response schema compatibility
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

@master_router.get("/whatsapp/{instance_name}/pairing-code")
async def get_pairing_code(
    instance_name: str,
    phone: str,
    master: Annotated[AdminUser, Depends(_require_master_admin)],
    db: AsyncSession = Depends(get_db),
):
    """Get a pairing code to connect WhatsApp without scanning QR."""
    # Ensure phone is numeric only
    clean_phone = re.sub(r"\D", "", phone)
    if not clean_phone:
        raise HTTPException(status_code=400, detail="Invalid phone number format.")
        
    instance = await db.scalar(select(EvolutionInstance).where(EvolutionInstance.instance_name == instance_name))
    custom_url = instance.evolution_api_url if instance else None
    custom_key = instance.evolution_api_key if instance else None

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
    """Delete a WhatsApp instance from Evolution API and DB."""
    instance = await db.scalar(select(EvolutionInstance).where(EvolutionInstance.instance_name == instance_name))
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found in database.")
        
    # Call Evolution API to delete
    evo_response = await evolution_service.delete_instance(
        instance_name,
        custom_url=instance.evolution_api_url,
        custom_key=instance.evolution_api_key
    )
    if "error" in evo_response:
        # Pelo menos logamos e tentamos remover do banco mesmo se falhar na api (ex: já deletada)
        logger.warning(f"Evolution API Error on delete: {evo_response['error']} - Proceeding with DB cleanup.")
         
    # Exclui do banco
    await db.delete(instance)
    await db.commit()
    return None
