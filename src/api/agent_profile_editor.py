"""
Agent Profile Editor API — Sprint 2

Permite ao comerciante configurar a personalidade do seu agente de atendimento
unicaomente via campos estruturados — sem precisar escrever prompts.

Endpoints:
  GET    /api/v1/agent/profile          — obter perfil atual
  PUT    /api/v1/agent/profile          — atualizar perfil
  POST   /api/v1/agent/profile/preview  — testar personalidade com mensagem de exemplo
  POST   /api/v1/agent/profile/activate — ativar perfil (publica o agente)
  GET    /api/v1/agent/profile/templates — listar templates de nicho
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.middleware.tenant_context import get_current_tenant_id
from src.models.database import async_session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/agent", tags=["Agent Profile Editor"])


# ─────────────────────────────────────────────────────────
# SCHEMAS
# ─────────────────────────────────────────────────────────

class AgentProfileUpdate(BaseModel):
    """Todos os campos são opcionais — atualiza apenas o que for enviado."""
    agent_name_display: Optional[str] = Field(None, description="Nome do agente. Ex: Max, Sofia, Lia")
    agent_avatar: Optional[str] = Field(None, description="Emoji do agente. Ex: 🤖, 👨‍💼, 👩‍💻")
    niche: Optional[str] = Field(None, description="Nicho: auto_eletrica, clinica, salao, contabilidade, loja, generic")
    tone: Optional[str] = Field(None, description="Tom: formal, amigavel, tecnico, descontraido, neutro")
    formality: Optional[str] = Field(None, description="Formalidade: muito_formal, equilibrado, informal")
    autonomy_level: Optional[str] = Field(None, description="Autonomia: conservadora, equilibrada, proativa")
    objective: Optional[str] = Field(None, max_length=300, description="Objetivo principal do agente")
    target_audience: Optional[str] = Field(None, max_length=300, description="Público-alvo")
    data_to_collect: Optional[list[str]] = Field(None, description="Dados que o agente deve coletar. Ex: ['nome', 'telefone', 'problema']")
    constraints: Optional[str] = Field(None, description="O que o agente NÃO deve fazer ou discutir")
    service_hours: Optional[str] = Field(None, description="Horário de atendimento. Ex: Seg-Sex 8h-18h")
    escalation_keywords: Optional[list[str]] = Field(None, description="Palavras que acionam escalada para humano")
    forbidden_topics: Optional[list[str]] = Field(None, description="Tópicos proibidos")
    welcome_message: Optional[str] = Field(None, description="Mensagem de boas-vindas personalizada")


class AgentProfileResponse(BaseModel):
    id: int
    agent_name_display: Optional[str]
    agent_avatar: Optional[str]
    niche: str
    tone: str
    formality: str
    autonomy_level: str
    objective: Optional[str]
    target_audience: Optional[str]
    data_to_collect: Optional[list]
    constraints: Optional[str]
    is_active: bool
    preview_prompt: Optional[str] = None  # prompt gerado, visível para debug

    class Config:
        from_attributes = True


class PreviewRequest(BaseModel):
    test_message: str = Field(..., description="Mensagem de teste para simular como o agente responderia")


class PreviewResponse(BaseModel):
    simulated_response: str
    generated_prompt_preview: str


# ─────────────────────────────────────────────────────────
# TEMPLATES DE NICHO
# ─────────────────────────────────────────────────────────

NICHE_TEMPLATES = {
    "auto_eletrica": {
        "agent_name_display": "Max",
        "agent_avatar": "🔧",
        "tone": "amigavel",
        "formality": "equilibrado",
        "autonomy_level": "equilibrada",
        "objective": "Recepcionar clientes, coletar informações do veículo e agendar visitas",
        "target_audience": "Donos de veículos com problemas elétricos",
        "data_to_collect": ["nome", "telefone", "modelo_veiculo", "ano", "problema_descricao"],
        "escalation_keywords": ["urgente", "parado", "não liga", "socorro", "acidente"],
        "welcome_message": "Olá! 👋 Aqui é o Max da {business_name}. Como posso te ajudar com seu veículo hoje?",
    },
    "clinica": {
        "agent_name_display": "Sofia",
        "agent_avatar": "🩺",
        "tone": "formal",
        "formality": "muito_formal",
        "autonomy_level": "conservadora",
        "objective": "Agendar consultas, tirar dúvidas sobre especialidades e orientar sobre documentação",
        "target_audience": "Pacientes e responsáveis",
        "data_to_collect": ["nome_completo", "data_nascimento", "telefone", "convenio", "especialidade_desejada"],
        "escalation_keywords": ["emergência", "urgência", "dor intensa", "febre alta", "acidente"],
        "welcome_message": "Bom dia! Sou a Sofia, assistente virtual da {business_name}. Como posso auxiliá-lo(a)?",
    },
    "salao": {
        "agent_name_display": "Lia",
        "agent_avatar": "✂️",
        "tone": "descontraido",
        "formality": "informal",
        "autonomy_level": "proativa",
        "objective": "Agendar horários, informar serviços e preços, confirmar agendamentos",
        "target_audience": "Clientes de salão de beleza",
        "data_to_collect": ["nome", "telefone", "servico_desejado", "data_hora_preferida"],
        "escalation_keywords": ["cancelar", "reclamação", "problema"],
        "welcome_message": "Oi! 💇 Sou a Lia do {business_name}. Qual serviço você gostaria de agendar?",
    },
    "contabilidade": {
        "agent_name_display": "Ricardo",
        "agent_avatar": "📊",
        "tone": "formal",
        "formality": "muito_formal",
        "autonomy_level": "conservadora",
        "objective": "Recepcionar clientes, verificar documentação necessária e agendar reuniões com contadores",
        "target_audience": "Empresas e empreendedores",
        "data_to_collect": ["nome", "empresa", "cnpj", "telefone", "assunto"],
        "escalation_keywords": ["fiscal", "multa", "autuação", "urgente", "prazo"],
        "welcome_message": "Olá! Sou o Ricardo, assistente virtual da {business_name}. Como posso ajudá-lo?",
    },
    "loja": {
        "agent_name_display": "Ana",
        "agent_avatar": "🛍️",
        "tone": "amigavel",
        "formality": "equilibrado",
        "autonomy_level": "proativa",
        "objective": "Auxiliar clientes com produtos, preços, disponibilidade e pedidos",
        "target_audience": "Clientes da loja",
        "data_to_collect": ["nome", "telefone", "produto_interesse", "endereco_entrega"],
        "escalation_keywords": ["reclamação", "troca", "devolução", "cancelar pedido"],
        "welcome_message": "Olá! 🛍️ Sou a Ana da {business_name}. Posso te ajudar a encontrar o que procura?",
    },
    "generic": {
        "agent_name_display": "Max",
        "agent_avatar": "🤖",
        "tone": "amigavel",
        "formality": "equilibrado",
        "autonomy_level": "equilibrada",
        "objective": "Recepcionar clientes e direcionar para o atendimento correto",
        "target_audience": "Clientes em geral",
        "data_to_collect": ["nome", "telefone", "assunto"],
        "escalation_keywords": ["urgente", "reclamação", "cancelar", "falar com humano"],
        "welcome_message": "Olá! Sou o assistente virtual da {business_name}. Como posso te ajudar?",
    },
}


# ─────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────

def _build_system_prompt(profile) -> str:
    """
    Transforma os campos estruturados do AgentProfile em um system prompt
    coeso para o LLM. O comerciante nunca vê ou edita o prompt diretamente.
    """
    name = getattr(profile, "agent_name_display", None) or getattr(profile, "name", "Assistente")
    tone_map = {
        "formal": "sempre formal e profissional",
        "amigavel": "amigável e acolhedor",
        "tecnico": "técnico e preciso",
        "descontraido": "descontraído e próximo",
        "neutro": "neutro e objetivo",
    }
    tone_desc = tone_map.get(getattr(profile, "tone", "neutro"), "neutro e objetivo")

    autonomy_map = {
        "conservadora": "Só responda o que tem certeza. Em caso de dúvida, escale para humano.",
        "equilibrada": "Tente resolver, mas escale quando necessário.",
        "proativa": "Seja proativo, sugira próximos passos e tente resolver sem escalar.",
    }
    autonomy_desc = autonomy_map.get(getattr(profile, "autonomy_level", "equilibrada"), "")

    data_fields = getattr(profile, "data_to_collect", []) or []
    constraints = getattr(profile, "constraints", "") or ""
    objective = getattr(profile, "objective", "") or ""
    audience = getattr(profile, "target_audience", "") or ""

    prompt = f"""Você é {name}, assistente virtual de atendimento ao cliente.

Seu tom é {tone_desc}.
Seu objetivo principal: {objective or 'Atender clientes com eficiência e cordialidade.'}
Público-alvo: {audience or 'Clientes em geral.'}

Durante o atendimento, colete as seguintes informações: {', '.join(data_fields) if data_fields else 'nome e telefone'}.

{autonomy_desc}
"""

    if constraints:
        prompt += f"\nRESTRIÇÕES IMPORTANTES:\n{constraints}\n"

    prompt += "\nResponda sempre em português brasileiro. Seja conciso e direto."
    return prompt


# ─────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────

@router.get(
    "/profile",
    response_model=AgentProfileResponse,
    summary="Obter perfil atual do agente",
)
async def get_agent_profile(
    tenant_id: int = Depends(get_current_tenant_id),
):
    """Retorna o perfil de personalidade configurado para o agente do tenant."""
    from src.models.agent_profile import AgentProfile

    async with async_session() as db:
        result = await db.execute(
            select(AgentProfile).where(
                AgentProfile.tenant_id == tenant_id,
                AgentProfile.is_active == True,
            )
        )
        profile = result.scalar_one_or_none()

        if not profile:
            # Retorna perfil padrão se não configurado
            result2 = await db.execute(
                select(AgentProfile).where(AgentProfile.tenant_id == tenant_id)
            )
            profile = result2.scalar_one_or_none()

        if not profile:
            raise HTTPException(status_code=404, detail="Perfil do agente não configurado. Complete o onboarding.")

        resp = AgentProfileResponse.model_validate(profile)
        resp.preview_prompt = _build_system_prompt(profile)
        return resp


@router.put(
    "/profile",
    response_model=AgentProfileResponse,
    summary="Atualizar personalidade do agente",
)
async def update_agent_profile(
    payload: AgentProfileUpdate,
    tenant_id: int = Depends(get_current_tenant_id),
):
    """Atualiza os campos de personalidade. Apenas campos enviados são alterados."""
    from src.models.agent_profile import AgentProfile

    async with async_session() as db:
        result = await db.execute(
            select(AgentProfile).where(AgentProfile.tenant_id == tenant_id)
        )
        profile = result.scalar_one_or_none()

        if not profile:
            raise HTTPException(status_code=404, detail="Perfil não encontrado.")

        update_data = payload.model_dump(exclude_none=True)
        for field, value in update_data.items():
            if hasattr(profile, field):
                setattr(profile, field, value)

        # Regenerar base_prompt automaticamente
        profile.base_prompt = _build_system_prompt(profile)

        await db.commit()
        await db.refresh(profile)

        logger.info("[AgentEditor] Perfil atualizado para tenant %s", tenant_id)

        resp = AgentProfileResponse.model_validate(profile)
        resp.preview_prompt = profile.base_prompt
        return resp


@router.post(
    "/profile/preview",
    response_model=PreviewResponse,
    summary="Testar personalidade com mensagem de exemplo",
)
async def preview_agent(
    payload: PreviewRequest,
    tenant_id: int = Depends(get_current_tenant_id),
):
    """
    Simula como o agente responderia a uma mensagem de teste
    com as configurações atuais, sem afetar conversas reais.
    """
    from src.models.agent_profile import AgentProfile
    from src.services.llm_service import LLMService

    async with async_session() as db:
        result = await db.execute(
            select(AgentProfile).where(AgentProfile.tenant_id == tenant_id)
        )
        profile = result.scalar_one_or_none()

        if not profile:
            raise HTTPException(status_code=404, detail="Perfil não encontrado.")

        system_prompt = _build_system_prompt(profile)

        try:
            llm = LLMService()
            response = await llm.chat(
                system_prompt=system_prompt,
                user_message=payload.test_message,
            )
        except Exception as e:
            logger.error("[AgentEditor] Preview falhou: %s", e)
            response = "[Erro ao gerar preview — verifique as configurações do LLM]"

        return PreviewResponse(
            simulated_response=response,
            generated_prompt_preview=system_prompt[:500] + "...",
        )


@router.post(
    "/profile/activate",
    summary="Ativar perfil (publicar agente)",
)
async def activate_agent_profile(
    tenant_id: int = Depends(get_current_tenant_id),
):
    """Marca o perfil como ativo. A partir daqui o agente começa a atender."""
    from src.models.agent_profile import AgentProfile

    async with async_session() as db:
        result = await db.execute(
            select(AgentProfile).where(AgentProfile.tenant_id == tenant_id)
        )
        profile = result.scalar_one_or_none()

        if not profile:
            raise HTTPException(status_code=404, detail="Perfil não encontrado.")

        profile.is_active = True
        profile.base_prompt = _build_system_prompt(profile)
        await db.commit()

        logger.info("[AgentEditor] Agente ativado para tenant %s", tenant_id)
        return {"status": "active", "message": f"Agente '{profile.agent_name_display or profile.name}' publicado com sucesso."}


@router.get(
    "/profile/templates",
    summary="Listar templates de nicho disponíveis",
)
async def list_niche_templates():
    """Retorna os templates prontos por nicho para acelerar o onboarding."""
    return {
        "templates": [
            {
                "niche": niche,
                "agent_name": data["agent_name_display"],
                "avatar": data["agent_avatar"],
                "objective": data["objective"],
                "tone": data["tone"],
            }
            for niche, data in NICHE_TEMPLATES.items()
        ]
    }


@router.post(
    "/profile/apply-template/{niche}",
    response_model=AgentProfileResponse,
    summary="Aplicar template de nicho ao perfil",
)
async def apply_niche_template(
    niche: str,
    tenant_id: int = Depends(get_current_tenant_id),
):
    """
    Aplica um template de nicho ao perfil atual.
    Sobrescreve os campos do template mas mantém o que o comerciante já personalizou.
    """
    from src.models.agent_profile import AgentProfile

    if niche not in NICHE_TEMPLATES:
        raise HTTPException(
            status_code=400,
            detail=f"Template '{niche}' não encontrado. Opções: {list(NICHE_TEMPLATES.keys())}"
        )

    template = NICHE_TEMPLATES[niche]

    async with async_session() as db:
        result = await db.execute(
            select(AgentProfile).where(AgentProfile.tenant_id == tenant_id)
        )
        profile = result.scalar_one_or_none()

        if not profile:
            raise HTTPException(status_code=404, detail="Perfil não encontrado. Complete o onboarding primeiro.")

        for field, value in template.items():
            if hasattr(profile, field):
                setattr(profile, field, value)

        profile.niche = niche
        profile.base_prompt = _build_system_prompt(profile)
        await db.commit()
        await db.refresh(profile)

        logger.info("[AgentEditor] Template '%s' aplicado para tenant %s", niche, tenant_id)

        resp = AgentProfileResponse.model_validate(profile)
        resp.preview_prompt = profile.base_prompt
        return resp
