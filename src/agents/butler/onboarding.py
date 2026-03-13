"""
Onboarding — Butler Agent Skill Module

State-machine-based tenant onboarding guide.
Tracks 5 steps: channel → QR code → IA config → funnel → verify.
Returns progress percentage and next instructions.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class OnboardingStep(str, Enum):
    channel_connect = "channel_connect"  # Step 1
    qr_scan = "qr_scan"  # Step 2
    ai_config = "ai_config"  # Step 3
    funnel_setup = "funnel_setup"  # Step 4
    verification = "verification"  # Step 5
    completed = "completed"  # Done


STEP_ORDER = [
    OnboardingStep.channel_connect,
    OnboardingStep.qr_scan,
    OnboardingStep.ai_config,
    OnboardingStep.funnel_setup,
    OnboardingStep.verification,
    OnboardingStep.completed,
]

STEP_INSTRUCTIONS = {
    OnboardingStep.channel_connect: (
        "🔌 *Passo 1 — Conectar Canal*\n\n"
        "1. Acesse o Portal → Canais → *+ Novo Canal*\n"
        "2. Selecione **WhatsApp** ou **Telegram**\n"
        "3. Dê um nome ao canal (ex: 'Atendimento Principal')\n"
        "4. Clique em *Criar* e prossiga para a leitura do QR Code."
    ),
    OnboardingStep.qr_scan: (
        "📲 *Passo 2 — Leitura do QR Code*\n\n"
        "1. Abra o WhatsApp no celular que será usado para atendimento\n"
        "2. Vá em: *⋮ → Dispositivos conectados → Conectar dispositivo*\n"
        "3. Aponte a câmera para o QR Code exibido no portal\n"
        "4. Aguarde a confirmação (até 30 segundos)\n\n"
        "⚠️ Use um número exclusivo para a loja — não use seu número pessoal."
    ),
    OnboardingStep.ai_config: (
        "🤖 *Passo 3 — Configurar o Agente de IA*\n\n"
        "1. Portal → *IA Config* → Personagem\n"
        "2. Defina o nome do agente (ex: 'Vendas Auto')\n"
        "3. Escolha o tom de voz (recomendado: Amigável + Profissional)\n"
        "4. Configure o prompt base com informações da sua loja\n"
        "5. Salve e envie uma mensagem de teste pelo WhatsApp conectado."
    ),
    OnboardingStep.funnel_setup: (
        "📋 *Passo 4 — Configurar o Funil de Atendimento*\n\n"
        "1. Portal → *Automações* → Novo Fluxo\n"
        "2. Crie estágios: Boas-vindas → Qualificação → Proposta → Fechamento\n"
        "3. Defina mensagens automáticas para cada etapa\n"
        "4. Ative o fluxo e associe ao canal conectado."
    ),
    OnboardingStep.verification: (
        "✅ *Passo 5 — Verificação Final*\n\n"
        "Checklist:\n"
        "☐ Canal WhatsApp aparece como *Conectado* (ícone verde)\n"
        "☐ Agente responde mensagens de teste corretamente\n"
        "☐ Funil criado e ativo\n"
        "☐ Notificações configuradas\n\n"
        "Se tudo estiver verde, seu sistema está pronto para atendimento! 🎉"
    ),
    OnboardingStep.completed: "🎉 *Onboarding concluído!* Seu sistema está totalmente configurado.",
}


@dataclass
class OnboardingState:
    tenant_id: int
    current_step: OnboardingStep = OnboardingStep.channel_connect
    completed_steps: list = field(default_factory=list)

    @property
    def progress_pct(self) -> int:
        done = len(self.completed_steps)
        return min(round(done / (len(STEP_ORDER) - 1) * 100), 100)

    @property
    def is_complete(self) -> bool:
        return self.current_step == OnboardingStep.completed

    @property
    def next_instruction(self) -> str:
        return STEP_INSTRUCTIONS.get(self.current_step, "Onboarding finalizado.")

    def advance(self) -> "OnboardingState":
        """Mark current step complete and advance to next."""
        idx = STEP_ORDER.index(self.current_step)
        if idx < len(STEP_ORDER) - 1:
            self.completed_steps.append(self.current_step.value)
            self.current_step = STEP_ORDER[idx + 1]
        return self

    def to_dict(self) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "current_step": self.current_step.value,
            "completed_steps": self.completed_steps,
            "progress_pct": self.progress_pct,
            "is_complete": self.is_complete,
            "instruction": self.next_instruction,
        }


# In-memory state store (for simplicity; can be persisted to DB later)
_onboarding_states: dict[int, OnboardingState] = {}


def get_or_create_state(tenant_id: int) -> OnboardingState:
    if tenant_id not in _onboarding_states:
        _onboarding_states[tenant_id] = OnboardingState(tenant_id=tenant_id)
        logger.info(f"Onboarding started for tenant #{tenant_id}")
    return _onboarding_states[tenant_id]


def advance_onboarding(tenant_id: int) -> OnboardingState:
    state = get_or_create_state(tenant_id)
    state.advance()
    logger.info(f"Onboarding tenant #{tenant_id} → step: {state.current_step.value}")
    return state


def reset_onboarding(tenant_id: int) -> OnboardingState:
    _onboarding_states[tenant_id] = OnboardingState(tenant_id=tenant_id)
    return _onboarding_states[tenant_id]
