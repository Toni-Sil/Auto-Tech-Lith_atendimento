"""
Conhecimento de Nicho para o Agente MAX.
Este módulo contém informações específicas sobre diferentes setores de negócios
para personalizar o atendimento.
"""

from typing import Optional

NICHE_KNOWLEDGE = {
    "default": {
        "pain_points": [
            "Falta de tempo para atender clientes",
            "Dificuldade em organizar agenda",
            "Perda de leads por demora no atendimento"
        ],
        "vocabulary": ["atendimento", "agendamento", "automação", "eficiência"],
        "benefits": "automatizar seu atendimento e garantir que nenhum cliente fique sem resposta"
    },
    "ecommerce_moda": {
        "pain_points": [
            "Muitas perguntas repetitivas sobre tamanho e medidas",
            "Dullvidas sobre troca e devolução",
            "Cliente quer saber sobre rastreio o tempo todo",
            "Sazonalidade e estoque parado"
        ],
        "vocabulary": ["grade de tamanhos", "tabela de medidas", "troca fácil", "coleção nova", "envio imediato"],
        "benefits": "automatizar o suporte sobre tamanhos e rastreio, liberando sua equipe para focar em vendas complexas"
    },
    "clinica_estetica": {
        "pain_points": [
            "Faltas e cancelamentos em cima da hora (no-show)",
            "Dúvidas sobre procedimentos e pós-operatório",
            "Reagendamentos constantes"
        ],
        "vocabulary": ["avaliação gratuita", "procedimento", "harmonização", "protocolo", "biomedicina"],
        "benefits": "reduzir o no-show com confirmações automáticas e tirar dúvidas sobre procedimentos 24h por dia"
    },
    "imobiliaria": {
        "pain_points": [
            "Qualificação de leads (muito curioso, pouco comprador)",
            "Agendamento de visitas improdutivas",
            "Dúvidas sobre documentação e financiamento"
        ],
        "vocabulary": ["visita", "financiamento", "imóvel na planta", "locação", "vistoria"],
        "benefits": "qualificar os leads antes de passar para o corretor e agendar visitas apenas com clientes reais"
    },
    "restaurante_delivery": {
        "pain_points": [
            "Pico de atendimento no horário de almoço/jantar",
            "Erros no pedido por falha de comunicação",
            "Demora para responder WhatsApp derruba vendas"
        ],
        "vocabulary": ["cardápio digital", "entrega grátis", "combo", "taxa de entrega", "ifood"],
        "benefits": "atender todos os pedidos simultaneamente nos horários de pico sem deixar ninguém esperando"
    },
    "advocacia": {
        "pain_points": [
            "Clientes ansiosos por status de processo",
            "Filtrar casos que não são da área de atuação",
            "Agendamento de consultas iniciais"
        ],
        "vocabulary": ["consulta jurídica", "processo", "andamento", "honorários", "causa"],
        "benefits": "filtrar os casos que realmente interessam e dar status de processos de forma automática"
    }
}

def get_niche_data(niche: Optional[str] = None) -> dict:
    """Retorna dados do nicho ou default se não encontrado."""
    if not niche:
        return NICHE_KNOWLEDGE["default"]
    
    # Normalização simples da string de busca
    niche_key = niche.lower().replace(" ", "_").replace("-", "_")
    
    # Tenta encontrar correspondência exata ou parcial
    for key, data in NICHE_KNOWLEDGE.items():
        if key == niche_key or key in niche_key or niche_key in key:
            return data
            
    return NICHE_KNOWLEDGE["default"]
