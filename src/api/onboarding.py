"""
Onboarding API — Sprint 1

Wizard de 3 passos para ativar um novo tenant em menos de 10 minutos.

Fluxo:
  POST /api/onboarding/register     → Cria tenant + admin
  POST /api/onboarding/channel      → Conecta WhatsApp (Evolution API)
  POST /api/onboarding/personality  → Configura personalidade do agente
  POST /api/onboarding/publish      → Ativa o agente e finaliza onboarding

Cada passo retorna status + next_step para guiar o frontend.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import async_session

router = APIRouter(prefix="/api/onboarding", tags=["Onboarding"])


# ---------------------------------------------------------------------------
# Templates de nicho — aceleram setup para < 5 minutos
# ---------------------------------------------------------------------------

NICHE_TEMPLATES: dict[str, dict] = {
    "auto_eletrica": {
        "name": "Auto Elétrica",
        "agent_name": "Max",
        "tone": "profissional e técnico",
        "objective": "Qualificar clientes, agendar visitas e orçamentos para serviços de auto elétrica.",
        "greeting": "Olá! Sou o Max, assistente da {company_name}. Como posso te ajudar hoje? 🚗⚡",
        "qualification_questions": [
            "Qual o problema que está acontecendo com o veículo?",
            "Qual o modelo e ano do carro?",
            "Você está em qual região?",
        ],
        "forbidden_topics": ["política", "religião", "concorrentes"],
        "handoff_triggers": ["orçamento", "urgente", "socorro", "acidente", "quebrado na rua"],
        "business_hours": {"start": "08:00", "end": "18:00", "days": ["seg", "ter", "qua", "qui", "sex", "sab"]},
    },
    "clinica": {
        "name": "Clínica",
        "agent_name": "Sofia",
        "tone": "acolhedor e empático",
        "objective": "Agendar consultas, informar sobre especialidades e acolher pacientes.",
        "greeting": "Olá! Sou a Sofia, assistente da {company_name}. Posso te ajudar a agendar uma consulta? 🏥",
        "qualification_questions": [
            "Qual especialidade você precisa?",
            "Você é paciente novo ou já tem cadastro?",
            "Tem preferência de horário?",
        ],
        "forbidden_topics": ["diagnóstico médico", "prescrição", "bula de remédio"],
        "handoff_triggers": ["emergência", "urgente", "dor forte", "sangramento", "febre alta"],
        "business_hours": {"start": "07:00", "end": "19:00", "days": ["seg", "ter", "qua", "qui", "sex"]},
    },
    "salao": {
        "name": "Salão de Beleza",
        "agent_name": "Luna",
        "tone": "descontraído e animado",
        "objective": "Agendar serviços de beleza, informar sobre preços e disponibilidade.",
        "greeting": "Oi, linda(o)! 💅 Sou a Luna do {company_name}. Quer agendar seu horário?",
        "qualification_questions": [
            "Qual serviço você deseja? (corte, coloração, manicure...)",
            "Tem preferência de profissional?",
            "Qual dia e horário te funciona melhor?",
        ],
        "forbidden_topics": ["política", "religião"],
        "handoff_triggers": ["reclamação", "erro no serviço", "reembolso", "gerente"],
        "business_hours": {"start": "09:00", "end": "20:00", "days": ["ter", "qua", "qui", "sex", "sab"]},
    },
    "contabilidade": {
        "name": "Escritório Contábil",
        "agent_name": "Bruno",
        "tone": "formal e objetivo",
        "objective": "Qualificar empresas que precisam de serviços contábeis e agendar reunião de diagnóstico.",
        "greeting": "Olá! Sou o Bruno, assistente da {company_name}. Posso te ajudar com informações sobre nossos serviços contábeis?",
        "qualification_questions": [
            "Qual o porte da sua empresa? (MEI, ME, EPP...)",
            "Qual o principal serviço que você precisa?",
            "Você já tem contador atualmente?",
        ],
        "forbidden_topics": ["conselho jurídico", "sonegação", "crimes fiscais"],
        "handoff_triggers": ["contrato", "proposta", "reunião", "preço", "valor"],
        "business_hours": {"start": "08:00", "end": "18:00", "days": ["seg", "ter", "qua", "qui", "sex"]},
    },
    "comercio": {
        "name": "Comércio Geral",
        "agent_name": "Alex",
        "tone": "amigável e prestativo",
        "objective": "Tirar dúvidas sobre produtos, preços, disponibilidade e processar pedidos.",
        "greeting": "Olá! Sou o Alex da {company_name}. Como posso te ajudar hoje? 🛍️",
        "qualification_questions": [
            "O que você está procurando?",
            "Você prefere retirar ou receber em casa?",
        ],
        "forbidden_topics": ["política", "religião"],
        "handoff_triggers": ["reclamação", "troca", "devolução", "problema", "falar com atendente"],
        "business_hours": {"start": "08:00", "end": "18:00", "days": ["seg", "ter", "qua", "qui", "sex", "sab"]},
    },
}


# ---------------------------------------------------------------------------
# Schemas Pydantic
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    company_name: str = Field(..., min_length=2, max_length=100)
    admin_name: str = Field(..., min_length=2, max_length=100)
    admin_email: EmailStr
    admin_password: str = Field(..., min_length=8)
    niche: Literal["auto_eletrica", "clinica", "salao", "contabilidade", "comercio", "custom"]
    subdomain: str = Field(..., min_length=3, max_length=50, pattern=r'^[a-z0-9-]+$')


class ChannelRequest(BaseModel):
    tenant_id: int
    evolution_instance_name: str
    evolution_api_url: str
    evolution_api_key: str
    operator_phone: str = Field(..., description="Telefone do operador para alertas do Butler")


class PersonalityRequest(BaseModel):
    tenant_id: int
    agent_name: str = Field(..., max_length=50)
    tone: str = Field(..., max_length=100)
    objective: str = Field(..., max_length=500)
    greeting: str = Field(..., max_length=300)
    qualification_questions: list[str] = Field(..., max_items=5)
    forbidden_topics: list[str] = Field(default_factory=list)
    handoff_triggers: list[str] = Field(..., description="Keywords que ativam escalada para humano")
    business_hours: dict = Field(..., description="{start, end, days[]}")
    use_template: Optional[str] = None


class PublishRequest(BaseModel):
    tenant_id: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/register", status_code=201)
async def onboarding_register(req: RegisterRequest):
    """
    Passo 1: Cria tenant + admin.
    Retorna tenant_id + token temporário para os próximos passos.
    """
    async with async_session() as db:
        # Verificar subdomain disponível
        exists = await db.execute(
            text("SELECT id FROM tenants WHERE subdomain = :s"),
            {"s": req.subdomain},
        )
        if exists.fetchone():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Subdomínio '{req.subdomain}' já está em uso.",
            )

        # Criar tenant
        result = await db.execute(
            text("""
                INSERT INTO tenants (name, subdomain, status, is_active, created_at)
                VALUES (:name, :subdomain, 'onboarding', true, NOW())
                RETURNING id
            """),
            {"name": req.company_name, "subdomain": req.subdomain},
        )
        tenant_id = result.fetchone()[0]

        # Hash da senha
        from passlib.hash import bcrypt
        hashed = bcrypt.hash(req.admin_password)

        # Criar admin
        await db.execute(
            text("""
                INSERT INTO admin_users (tenant_id, name, email, password_hash, role, created_at)
                VALUES (:tid, :name, :email, :pwd, 'owner', NOW())
            """),
            {"tid": tenant_id, "name": req.admin_name, "email": req.admin_email, "pwd": hashed},
        )

        # Criar quota inicial
        await db.execute(
            text("""
                INSERT INTO tenant_quotas (tenant_id, messages_limit, ai_calls_limit, messages_used, ai_calls_used)
                VALUES (:tid, 1000, 500, 0, 0)
            """),
            {"tid": tenant_id},
        )

        await db.commit()

    # Aplicar template de nicho se selecionado
    template = NICHE_TEMPLATES.get(req.niche, {})

    return {
        "step": "register",
        "status": "ok",
        "tenant_id": tenant_id,
        "next_step": "channel",
        "template_preview": template,
        "message": f"Tenant '{req.company_name}' criado com sucesso! Próximo: configure seu canal WhatsApp.",
    }


@router.post("/channel", status_code=200)
async def onboarding_channel(req: ChannelRequest):
    """
    Passo 2: Conecta o canal WhatsApp via Evolution API.
    Salva credenciais no Vault e configura webhook.
    """
    async with async_session() as db:
        # Salvar credenciais no vault (criptografadas em prod)
        await db.execute(
            text("""
                INSERT INTO vault_credentials (tenant_id, key_name, key_value, created_at)
                VALUES (:tid, 'evolution_api_key', :val, NOW())
                ON CONFLICT (tenant_id, key_name) DO UPDATE SET key_value = :val
            """),
            {"tid": req.tenant_id, "val": req.evolution_api_key},
        )

        # Registrar instância WhatsApp
        await db.execute(
            text("""
                INSERT INTO evolution_instances (tenant_id, instance_name, api_url, operator_phone, status, created_at)
                VALUES (:tid, :name, :url, :phone, 'pending', NOW())
                ON CONFLICT (tenant_id, instance_name) DO UPDATE
                SET api_url = :url, operator_phone = :phone
            """),
            {
                "tid": req.tenant_id,
                "name": req.evolution_instance_name,
                "url": req.evolution_api_url,
                "phone": req.operator_phone,
            },
        )

        await db.commit()

    return {
        "step": "channel",
        "status": "ok",
        "next_step": "personality",
        "message": "Canal configurado! Próximo: defina a personalidade do seu agente.",
    }


@router.post("/personality", status_code=200)
async def onboarding_personality(req: PersonalityRequest):
    """
    Passo 3: Configura personalidade do agente via campos estruturados.
    Se use_template for informado, os campos do template são aplicados como base.
    """
    # Merge com template se solicitado
    if req.use_template and req.use_template in NICHE_TEMPLATES:
        tmpl = NICHE_TEMPLATES[req.use_template]
        # Campos do request sobrescrevem o template
        final = {
            "agent_name": req.agent_name or tmpl["agent_name"],
            "tone": req.tone or tmpl["tone"],
            "objective": req.objective or tmpl["objective"],
            "greeting": req.greeting or tmpl["greeting"],
            "qualification_questions": req.qualification_questions or tmpl["qualification_questions"],
            "forbidden_topics": req.forbidden_topics or tmpl["forbidden_topics"],
            "handoff_triggers": req.handoff_triggers or tmpl["handoff_triggers"],
            "business_hours": req.business_hours or tmpl["business_hours"],
        }
    else:
        final = req.model_dump(exclude={"tenant_id", "use_template"})

    async with async_session() as db:
        await db.execute(
            text("""
                INSERT INTO agent_profiles (
                    tenant_id, name, tone, objective, greeting,
                    qualification_questions, forbidden_topics,
                    handoff_triggers, business_hours,
                    is_active, created_at
                ) VALUES (
                    :tid, :name, :tone, :objective, :greeting,
                    :qual::jsonb, :forbidden::jsonb,
                    :handoff::jsonb, :hours::jsonb,
                    false, NOW()
                )
                ON CONFLICT (tenant_id) DO UPDATE SET
                    name = :name, tone = :tone, objective = :objective,
                    greeting = :greeting,
                    qualification_questions = :qual::jsonb,
                    forbidden_topics = :forbidden::jsonb,
                    handoff_triggers = :handoff::jsonb,
                    business_hours = :hours::jsonb
            """),
            {
                "tid": req.tenant_id,
                "name": final["agent_name"],
                "tone": final["tone"],
                "objective": final["objective"],
                "greeting": final["greeting"],
                "qual": str(final["qualification_questions"]).replace("'", '"'),
                "forbidden": str(final["forbidden_topics"]).replace("'", '"'),
                "handoff": str(final["handoff_triggers"]).replace("'", '"'),
                "hours": str(final["business_hours"]).replace("'", '"'),
            },
        )
        await db.commit()

    return {
        "step": "personality",
        "status": "ok",
        "next_step": "publish",
        "config_preview": final,
        "message": f"Personalidade '{final['agent_name']}' configurada! Próximo: publique seu agente.",
    }


@router.post("/publish", status_code=200)
async def onboarding_publish(req: PublishRequest):
    """
    Passo 4: Ativa o agente e finaliza o onboarding.
    Muda status do tenant para 'active' e ativa o agent_profile.
    """
    async with async_session() as db:
        # Ativar agent profile
        await db.execute(
            text("UPDATE agent_profiles SET is_active = true WHERE tenant_id = :tid"),
            {"tid": req.tenant_id},
        )

        # Ativar tenant
        await db.execute(
            text("UPDATE tenants SET status = 'active', updated_at = NOW() WHERE id = :tid"),
            {"tid": req.tenant_id},
        )

        await db.commit()

    # Registrar onboarding no ButlerLog
    from src.agents.butler_agent import ButlerAction, ButlerAgent
    from src.models.butler_log import ButlerActionType, ButlerSeverity
    _butler = ButlerAgent()
    await _butler.log_action(ButlerAction(
        action_type=ButlerActionType.tenant_onboarding,
        severity=ButlerSeverity.low,
        description=f"Onboarding concluído. Tenant {req.tenant_id} ativado com sucesso.",
        tenant_id=req.tenant_id,
        meta={"completed_at": datetime.utcnow().isoformat()},
    ))

    return {
        "step": "publish",
        "status": "active",
        "next_step": None,
        "message": "🎉 Agente ativado! Seu atendimento automático está no ar.",
        "dashboard_url": f"/dashboard",
    }


@router.get("/templates", status_code=200)
async def list_templates():
    """Lista os templates de nicho disponíveis."""
    return {
        "templates": [
            {"id": k, "name": v["name"], "agent_name": v["agent_name"], "tone": v["tone"]}
            for k, v in NICHE_TEMPLATES.items()
        ]
    }
