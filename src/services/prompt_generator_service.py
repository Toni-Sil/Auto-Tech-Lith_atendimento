"""
PromptGeneratorService — Gera prompts de agente a partir de respostas de perguntas dinâmicas.
Inclui templates por nicho de mercado.
"""

import json
from datetime import datetime
from typing import Optional

from src.utils.logger import setup_logger

logger = setup_logger(__name__)

# ─────────────────────────────────────────────
# Templates base por nicho
# ─────────────────────────────────────────────
NICHE_TEMPLATES = {
    "geral": {
        "label": "Geral / Sem nicho específico",
        "intro": "Você é um assistente virtual especializado em atendimento ao cliente.",
        "data_defaults": ["Nome", "E-mail", "Telefone", "Descrição da demanda"],
    },
    "imobiliario": {
        "label": "Imobiliário",
        "intro": "Você é um corretor virtual especializado em imóveis. Seu objetivo é qualificar compradores, locatários e vendedores, entender suas necessidades e agendar visitas ou reuniões com a equipe.",
        "data_defaults": [
            "Nome",
            "Tipo de imóvel (compra/aluguel/venda)",
            "Região de interesse",
            "Faixa de valor",
            "Contato",
        ],
    },
    "saude": {
        "label": "Saúde e Bem-estar",
        "intro": "Você é um assistente virtual de uma clínica/consultório. Seu objetivo é acolher pacientes, tirar dúvidas sobre serviços, e agendar consultas ou exames com a equipe de saúde.",
        "data_defaults": [
            "Nome completo",
            "Data de nascimento",
            "Convênio",
            "Especialidade desejada",
            "Contato",
        ],
    },
    "educacao": {
        "label": "Educação e Cursos",
        "intro": "Você é um assistente de uma instituição educacional. Seu objetivo é apresentar cursos disponíveis, esclarecer dúvidas sobre método, valores e matrículas, e encaminhar interessados para a equipe de vendas.",
        "data_defaults": [
            "Nome",
            "Curso de interesse",
            "Disponibilidade de horário",
            "Forma de pagamento",
            "Contato",
        ],
    },
    "ecommerce": {
        "label": "E-commerce e Varejo",
        "intro": "Você é um assistente de vendas online. Seu objetivo é ajudar clientes a encontrar produtos, esclarecer dúvidas sobre pedidos, entregas e trocas, e direcionar para a finalização da compra.",
        "data_defaults": [
            "Nome",
            "Número do pedido (se houver)",
            "Produto de interesse",
            "Problema ou dúvida",
        ],
    },
    "tecnologia": {
        "label": "Tecnologia e SaaS",
        "intro": "Você é um agente de pré-venda e suporte técnico de uma empresa de tecnologia. Seu objetivo é entender a necessidade do lead, demonstrar o valor do produto e agendar uma demo com o time.",
        "data_defaults": [
            "Nome",
            "Empresa",
            "Cargo",
            "Desafio atual",
            "E-mail corporativo",
        ],
    },
    "financeiro": {
        "label": "Financeiro e Seguros",
        "intro": "Você é um consultor financeiro virtual. Seu objetivo é entender o perfil do cliente, apresentar soluções financeiras adequadas e agendar uma consultoria personalizada com um especialista.",
        "data_defaults": [
            "Nome",
            "Objetivo financeiro",
            "Renda aproximada",
            "Telefone de contato",
        ],
    },
    "juridico": {
        "label": "Jurídico e Advocacia",
        "intro": "Você é um atendente virtual de um escritório de advocacia. Seu objetivo é acolher o cliente, entender brevemente o caso e agendar uma consulta inicial com o advogado responsável.",
        "data_defaults": [
            "Nome completo",
            "Área do direito (ex: trabalhista, civil, família)",
            "Breve descrição do caso",
            "Contato",
        ],
    },
    "restaurante": {
        "label": "Restaurante e Food Service",
        "intro": "Você é um atendente virtual de um restaurante. Seu objetivo é tirar dúvidas sobre cardápio, horários de funcionamento, reservas e pedidos para entrega.",
        "data_defaults": [
            "Nome",
            "Tipo de atendimento (mesa/delivery)",
            "Número de pessoas (se reserva)",
            "Contato",
        ],
    },
    "automacao": {
        "label": "Automação e Agentes de IA",
        "intro": "Você é um agente de atendimento especializado em automação com inteligência artificial. Seu objetivo é entender a demanda do cliente, apresentar as soluções da empresa e agendar uma reunião de briefing.",
        "data_defaults": ["Nome", "E-mail", "Empresa", "Descrição da demanda"],
    },
}

# Mapa de tom para instrução de estilo
TONE_MAP = {
    "formal": "Mantenha um tom estritamente formal e profissional em todas as interações.",
    "semi-formal": "Use um tom semi-formal: educado e profissional, mas acessível e amigável.",
    "neutro": "Mantenha um tom neutro, claro e objetivo.",
    "amigavel": "Use um tom amigável, próximo e descontraído, como se fosse um amigo especialista.",
    "jovem": "Use linguagem moderna, informal e dinâmica, adequada para um público jovem.",
}

# Mapa de grau de autonomia para instrução
AUTONOMY_MAP = {
    "estrita": "Você NÃO tem autonomia para tomar decisões. Sempre direcione para um humano antes de qualquer ação.",
    "orientada": "Você tem autonomia mínima. Pode coletar informações e tirar dúvidas básicas, mas encaminhe decisões para humanos.",
    "equilibrada": "Você tem autonomia moderada. Pode coletar dados, tirar dúvidas e fazer agendamentos ou direcionamentos básicos.",
    "proativa": "Você tem autonomia elevada. Pode resolver a maioria dos casos sem intervenção humana, oferecer soluções e agir proativamente, exceto em situações críticas.",
    "independente": "Você tem autonomia máxima. Resolva o maior número possível de demandas de forma independente, tome decisões complexas e negocie com alta liberdade.",
}

# Mapa de formalidade para instrução
FORMALITY_MAP = {
    "muito_informal": "Use linguagem muito informal: emojis são super bem-vindos, use gírias, expressões descontraídas e seja bastante casual e solto.",
    "informal": "Use linguagem informal: seja próximo, colegial e use linguagem e expressões do dia a dia de forma amigável.",
    "equilibrado": "Use linguagem padrão: um tom equilibrado, profissional, mas claro e acessível para qualquer público sem ser rígido.",
    "formal": "Use linguagem formal e cuidada: evite gírias, seja respeitoso, polido, com vocabulário culto.",
    "muito_formal": "Use linguagem estritamente formal e impessoal: focado no corporativo tradicional, sem contrações, sem expressões coloquiais ou proximidade indevida.",
}


class PromptGeneratorService:

    def get_templates(self) -> list:
        """Retorna a lista de templates disponíveis por nicho."""
        return [
            {"key": key, "label": tmpl["label"], "data_defaults": tmpl["data_defaults"]}
            for key, tmpl in NICHE_TEMPLATES.items()
        ]

    def generate_prompt(self, answers: dict) -> str:
        """
        Gera um sistema de prompt estruturado a partir das respostas do wizard.

        Campos esperados em answers:
          - niche: str (key do NICHE_TEMPLATES)
          - tone: str (key do TONE_MAP)
          - formality: str (key do FORMALITY_MAP)
          - autonomy_level: str (key do AUTONOMY_MAP)
          - objective: str
          - target_audience: str
          - data_to_collect: list[str]
          - constraints: str
          - company_name: str (opcional)
          - agent_name: str (opcional)
        """
        niche_key = answers.get("niche", "geral")
        tmpl = NICHE_TEMPLATES.get(niche_key, NICHE_TEMPLATES["geral"])

        tone_key = answers.get("tone", "neutro")
        tone_instruction = TONE_MAP.get(tone_key, TONE_MAP["neutro"])

        formality = answers.get("formality", "equilibrado")
        formality_instruction = FORMALITY_MAP.get(
            formality, FORMALITY_MAP["equilibrado"]
        )

        autonomy = answers.get("autonomy_level", "equilibrada")
        autonomy_instruction = AUTONOMY_MAP.get(autonomy, AUTONOMY_MAP["equilibrada"])

        objective = answers.get("objective", "Atender e qualificar clientes.")
        target_audience = answers.get("target_audience", "Público geral.")
        constraints = answers.get("constraints", "Nenhuma restrição específica.")
        company_name = answers.get("company_name", "nossa empresa")
        agent_name = answers.get("agent_name", "Assistente")

        data_to_collect = answers.get("data_to_collect", tmpl["data_defaults"])
        if isinstance(data_to_collect, str):
            data_to_collect = [
                d.strip() for d in data_to_collect.split(",") if d.strip()
            ]
        data_list = "\n".join(f"  - {item}" for item in data_to_collect)

        prompt = f"""Você é {agent_name}, assistente virtual de {company_name}.
{tmpl['intro']}

### ESTILO DE COMUNICAÇÃO:
- **Tom:** {tone_instruction}
- **Formalidade:** {formality_instruction}

### PÚBLICO-ALVO:
{target_audience}

### OBJETIVO PRINCIPAL DO ATENDIMENTO:
{objective}

### NÍVEL DE AUTONOMIA:
{autonomy_instruction}

### DADOS A COLETAR DO CLIENTE (obrigatórios antes de avançar):
{data_list}

Se faltar QUALQUER um dos dados acima, solicite educadamente antes de prosseguir.
Use a ferramenta `update_customer_info` para registrar os dados coletados.

### RESTRIÇÕES E TEMAS PROIBIDOS:
{constraints}
Recuse educadamente qualquer assunto fora do escopo: "Não posso ajudar com isso. Vamos focar no seu atendimento?"

### DIRETRIZES FINAIS:
- Faça apenas UMA pergunta por vez.
- Seja CONCISO e OBJETIVO — evite textos longos.
- Nunca invente informações ou afirme o que não sabe com certeza.
- Se o cliente pedir para falar com um humano, transmita o recado à equipe.
- Data atual: {{date_now}}

Cliente atual:
- Nome: {{customer_name}}
- E-mail: {{customer_email}}
- Empresa: {{customer_company}}
"""
        logger.info(
            f"Prompt generated for niche='{niche_key}', tone='{tone_key}', formality='{formality}', autonomy='{autonomy}'"
        )
        return prompt.strip()

    async def analyze_prompt(self, base_prompt: str) -> dict:
        """
        Analisa um prompt base já escrito e extrai os campos estruturados do perfil de agente.

        Retorna um dict com os campos reconhecidos:
          niche, tone, formality, autonomy_level, objective,
          target_audience, data_to_collect, constraints

        Campos não identificáveis são retornados com valores padrão.
        """
        from src.services.llm_service import llm_service

        system = """Você é um analisador especializado em extrair metadados de prompts de agentes de IA.
Dado um texto de prompt de sistema (base_prompt), retorne SOMENTE um JSON válido com os seguintes campos:

{
  "name": "<nome do agente extraído ou 'Agente' se indefinido>",
  "niche": "<geral|imobiliario|saude|educacao|ecommerce|tecnologia|financeiro|juridico|restaurante|automacao>",
  "tone": "<formal|semi-formal|neutro|amigavel|jovem>",
  "formality": "<muito_informal|informal|equilibrado|formal|muito_formal>",
  "autonomy_level": "<estrita|orientada|equilibrada|proativa|independente>",
  "objective": "<resumo do objetivo principal em 1-2 frases>",
  "target_audience": "<descrição do público-alvo>",
  "data_to_collect": ["campo1", "campo2", "..."],
  "constraints": "<restrições e temas proibidos, ou vazio se não houver>"
}

Regras:
- Retorne APENAS o JSON, sem markdown, sem explicações.
- Se um campo não estiver claro no prompt, use o valor padrão mais adequado.
- Para `data_to_collect`, liste os dados que o prompt menciona coletar do cliente.
- Para `niche`, escolha a categoria mais próxima do domínio do agente."""

        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": f"Analise este prompt de agente e extraia os campos:\n\n{base_prompt}",
            },
        ]

        try:
            response = await llm_service.get_chat_response(messages, temperature=0.2)
            raw = response.content or "{}"
            # Limpar possíveis marcadores de código
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()
            result = json.loads(raw)
            # Ensure critical fields are strings to avoid validation errors
            for field in ["niche", "tone", "formality", "autonomy_level"]:
                if field in result:
                    result[field] = str(result[field])
            logger.info(
                f"analyze_prompt: campos extraídos → nicho={result.get('niche')}, tom={result.get('tone')}"
            )
            return result
        except Exception as e:
            logger.error(f"analyze_prompt: erro ao extrair campos do prompt: {e}")
            return {}


prompt_generator_service = PromptGeneratorService()
