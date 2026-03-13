"""
Support Triage — Butler Agent Skill Module

Classifies support tickets by urgency, auto-resolves known issues,
and returns structured recommendations for escalation or auto-response.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from src.utils.logger import setup_logger

logger = setup_logger(__name__)


# ── Urgency scoring keywords ──────────────────────────────────────────────────
CRITICAL_KEYWORDS = [
    r"\bsistema fora\b",
    r"\bsem acesso\b",
    r"\bnão funciona\b",
    r"\berro 500\b",
    r"\bqueda\b",
    r"\bdesconectou\b",
    r"\bperdeu dados\b",
    r"\bpagamento\b",
    r"\bcobranç\w+\b",
]
HIGH_KEYWORDS = [
    r"\bwhatsapp\b.*\bdesconect\w+",
    r"\bnão responde\b",
    r"\blento\b",
    r"\bQR\b",
    r"\binstância\b",
    r"\bIA\b.*\bparou\b",
]
MEDIUM_KEYWORDS = [
    r"\bnão receb\w+\b",
    r"\batualiz\w+\b",
    r"\bconfigurar?\b",
    r"\bentender\b",
]

# ── Auto-resolvable FAQ patterns ──────────────────────────────────────────────
FAQ_PATTERNS = {
    r"(como|onde).*(configurar|ativar).*(whatsapp|telegram|canal)": (
        "Para conectar um canal:\n"
        "1. Acesse Portal → Canais → Novo Canal\n"
        "2. Escaneie o QR Code com o WhatsApp do chip\n"
        "3. Aguarde confirmação (até 30s)\n"
        "Se persistir, verifique se a Evolution API está online."
    ),
    r"(como|onde).*(prompt|ia|agente).*(configur|alter|mud)": (
        "Para configurar o agente de IA:\n"
        "1. Portal → IA Config → Personagem\n"
        "2. Ajuste o prompt base e o tom de voz\n"
        "3. Salve e teste enviando uma mensagem de teste."
    ),
    r"(n[ãa]o|sem).*(receb|cheg).*(mensag|notif)": (
        "Verifique:\n"
        "• Status da instância WhatsApp (verde = conectado)\n"
        "• Webhook configurado corretamente em Configurações → Webhook\n"
        "• Consulte os logs em Configurações → Logs"
    ),
    r"(esquec|perdi|reset).*(senha|acesso)": (
        "Para resetar a senha:\n"
        "1. Tela de login → 'Esqueci minha senha'\n"
        "2. Informe o e-mail cadastrado\n"
        "3. Acesse o link enviado por e-mail\n"
        "Se não receber, contate o suporte master."
    ),
}


@dataclass
class TriageResult:
    ticket_id: Optional[int]
    urgency: str  # critical / high / medium / low
    urgency_score: int  # 0-100
    auto_resolved: bool
    auto_response: Optional[str]
    escalate: bool
    labels: list
    recommendation: str


def _score_text(text: str) -> tuple[int, list]:
    """Returns (score 0-100, matched labels)."""
    t = text.lower()
    score = 0
    labels = []

    for pat in CRITICAL_KEYWORDS:
        if re.search(pat, t):
            score += 35
            labels.append("critical_keyword")

    for pat in HIGH_KEYWORDS:
        if re.search(pat, t):
            score += 20
            labels.append("high_keyword")

    for pat in MEDIUM_KEYWORDS:
        if re.search(pat, t):
            score += 10
            labels.append("medium_keyword")

    return min(score, 100), list(set(labels))


def _auto_respond(text: str) -> Optional[str]:
    """Check if this ticket matches a known FAQ. Returns auto-response or None."""
    t = text.lower()
    for pattern, response in FAQ_PATTERNS.items():
        if re.search(pattern, t, re.IGNORECASE):
            return response
    return None


def triage_ticket(
    ticket_text: str,
    ticket_id: Optional[int] = None,
    tenant_id: Optional[int] = None,
) -> TriageResult:
    """
    Classify a support ticket by urgency and determine resolution path.
    Pure function — no I/O, safe to call anywhere.
    """
    score, labels = _score_text(ticket_text)
    auto_response = _auto_respond(ticket_text)

    if score >= 70:
        urgency = "critical"
        escalate = True
        recommendation = "🚨 Escalar imediatamente para o Master Admin"
    elif score >= 40:
        urgency = "high"
        escalate = True
        recommendation = "⚠️ Escalar para suporte humano em até 2 horas"
    elif score >= 20:
        urgency = "medium"
        escalate = False
        recommendation = "📋 Adicionar à fila padrão de suporte"
    else:
        urgency = "low"
        escalate = False
        recommendation = "ℹ️ Enviar resposta automática e fechar se não houver retorno"

    # FAQ auto-resolution overrides escalation for low/medium
    auto_resolved = bool(auto_response) and not escalate

    logger.info(
        f"Ticket #{ticket_id} triaged: urgency={urgency} score={score} "
        f"auto_resolved={auto_resolved} tenant={tenant_id}"
    )

    return TriageResult(
        ticket_id=ticket_id,
        urgency=urgency,
        urgency_score=score,
        auto_resolved=auto_resolved,
        auto_response=auto_response,
        escalate=escalate,
        labels=labels,
        recommendation=recommendation,
    )
