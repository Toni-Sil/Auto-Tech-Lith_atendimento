"""
Gerenciador de Prompts do MAX.
Responsável por carregar templates e injetar contexto dinâmico.
"""
from typing import Dict, List, Optional
from app.core.niche_knowledge import get_niche_data

class PromptManager:
    def __init__(self, template_path: str = "p:/agentes/dify/agent-prompt.md"):
        self.template_path = template_path
        self._template_cache: Optional[str] = None

    def _load_template(self) -> str:
        """Carrega o template do arquivo."""
        if self._template_cache:
            return self._template_cache
            
        try:
            with open(self.template_path, "r", encoding="utf-8") as f:
                self._template_cache = f.read()
            return self._template_cache
        except FileNotFoundError:
            # Fallback seguro se o arquivo não existir
            return """
            Você é MAX, assistente da Auto Tech Lith.
            Seu objetivo é atender clientes e agendar reuniões.
            CONTEXTO: {{NICHE_CONTEXT}}
            """

    def construct_system_prompt(self, 
                              client_name: str = "", 
                              company_niche: str = "", 
                              conversation_history: str = "") -> str:
        """
        Constrói o prompt final injetando contexto.
        
        Args:
            client_name (str): Nome do cliente (se souber).
            company_niche (str): Nicho da empresa do cliente.
            conversation_history (str): Resumo ou trechos relevantes anteriores.
        """
        template = self._load_template()
        niche_data = get_niche_data(company_niche)
        
        # Constrói o bloco de conhecimento de nicho
        niche_block = self._format_niche_block(niche_data, company_niche)
        
        # Constrói instruções de tom baseadas no histórico (simulado por enquanto)
        tone_block = self._detect_tone_and_create_instructions(conversation_history)
        
        # Injeção de variáveis
        # Se o template tiver os placeholders, substitui. Se não, anexa ao final (fallback).
        final_prompt = template
        
        if "{{NICHE_CONTEXT}}" in final_prompt:
            final_prompt = final_prompt.replace("{{NICHE_CONTEXT}}", niche_block)
        else:
            # Se não tiver placeholder, adiciona seção dinâmica antes das ferramentas
            final_prompt = final_prompt.replace("## FERRAMENTAS DISPONÍVEIS", 
                                              f"{niche_block}\n\n## FERRAMENTAS DISPONÍVEIS")

        if "{{TONE_INSTRUCTIONS}}" in final_prompt:
            final_prompt = final_prompt.replace("{{TONE_INSTRUCTIONS}}", tone_block)
        
        if "{{CLIENT_HISTORY}}" in final_prompt:
            final_prompt = final_prompt.replace("{{CLIENT_HISTORY}}", conversation_history)

        return final_prompt

    def _format_niche_block(self, data: dict, niche_name: str) -> str:
        """Formata os dados do nicho em markdown para o prompt."""
        if not niche_name:
            return ""
            
        pain_points = "\n- ".join(data.get("pain_points", []))
        vocabulary = ", ".join(data.get("vocabulary", []))
        benefits = data.get("benefits", "")
        
        return f"""
## CONHECIMENTO DE NICHO: {niche_name.upper()}
Você está falando com um cliente do setor de **{niche_name}**.
**Dores Comuns deste setor:**
- {pain_points}

**Vocabulário Técnico para usar:** {vocabulary}

**Seu Argumento de Venda:** Foque em como a automação pode {benefits}.
"""

    def _detect_tone_and_create_instructions(self, history: str) -> str:
        """
        Analisa o histórico para ajustar o tom (Lógica simples por keywords).
        """
        if not history:
            return ""
            
        lower_hist = history.lower()
        
        if any(x in lower_hist for x in ["urgente", "rápido", "demora", "logo"]):
            return "\n**TOM DE VOZ DETECTADO**: O cliente parece ter pressa. Seja extremamente direto e pule gentilezas desnecessárias. Vá direto ao ponto."
            
        if any(x in lower_hist for x in ["caro", "preço", "valor", "desconto"]):
            return "\n**TOM DE VOZ DETECTADO**: O cliente está focado em preço. Enfatize o ROI (Retorno sobre Investimento) e valor agregado antes de falar de números."
            
        if any(x in lower_hist for x in ["medo", "seguro", "garantia", "receio"]):
            return "\n**TOM DE VOZ DETECTADO**: O cliente está inseguro. Mostre autoridade, use casos de sucesso e transmita segurança."

        return ""
