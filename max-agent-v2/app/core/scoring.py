"""
Lead Scoring Core Logic.
Antigravity Skill: business-logic
"""
from typing import Dict, List, Any

class LeadScorer:
    """
    Calcula o score de um lead (0-100) baseado em critérios predefinidos.
    Critérios:
    - Budget (25pts)
    - Urgência (20pts)
    - Fit/Nicho (30pts)
    - Engajamento (25pts)
    """

    def calculate_score(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analisa o contexto e retorna o score total e breakdown.
        
        Args:
            context: Dicionário contendo:
                - history (str): Histórico da conversa
                - niche (str): Nicho identificado
                - interaction_count (int): Número de mensagens trocadas
                - has_phone (bool): Se temos o telefone (implícito se estamos falando no zap, mas vale reforçar)
        
        Returns:
            Dict com 'total_score' (int) e 'breakdown' (dict).
        """
        history = context.get("history", "").lower()
        niche = context.get("niche", "")
        interaction_count = context.get("interaction_count", 0)
        
        score_breakdown = {
            "budget": self._evaluate_budget(history),
            "urgency": self._evaluate_urgency(history),
            "fit": self._evaluate_fit(niche, history),
            "engagement": self._evaluate_engagement(interaction_count, history)
        }
        
        total_score = sum(score_breakdown.values())
        
        # Cap em 100 just in case
        total_score = min(100, total_score)
        
        return {
            "total_score": total_score,
            "breakdown": score_breakdown,
            "classification": self._classify_score(total_score)
        }

    def _evaluate_budget(self, text: str) -> int:
        """Avalia menção a orçamento (Max 25 pts)"""
        keywords_high = ["orçamento", "investimento", "quanto custa", "valor", "preço", "pagamento", "dinheiro", "custo"]
        keywords_specific = ["mil", "reais", "dólar", "contratar", "fechar", "assinar", "implantação"]
        
        score = 0
        
        # Mencionou palavras chave de dinheiro?
        if any(w in text for w in keywords_high):
            score += 15
            
        # Mencionou valores ou intenção clara de contratação?
        if any(w in text for w in keywords_specific):
            score += 10
            
        return min(25, score)

    def _evaluate_urgency(self, text: str) -> int:
        """Avalia urgência (Max 20 pts)"""
        keywords_urgent = ["urgente", "pra ontem", "rápido", "logo", "imediato", "hoje", "preciso agora", "perder", "perdendo", "prejuízo"]
        keywords_medium = ["semana que vem", "próximo mês", "analisando", "demora", "problema"]
        
        if any(w in text for w in keywords_urgent):
            return 20
        if any(w in text for w in keywords_medium):
            return 10
            
        return 0

    def _evaluate_fit(self, niche: str, text: str) -> int:
        """Avalia fit com o negócio (Max 30 pts)"""
        # Se temos um nicho identificado, já é um bom sinal
        score = 0
        if niche and niche.lower() not in ["", "desconhecido", "nicho não informado"]:
            score += 15
            
        # Palavras que indicam dores que a Auto Tech Lith resolve
        pain_keywords = [
            "atendimento", "automático", "agendamento", "site", "landing page", 
            "sistema", "bot", "inteligência artificial", "perder cliente", "demora",
            "zap", "whatsapp", "responder", "suporte"
        ]
        
        matches = sum(1 for w in pain_keywords if w in text)
        score += min(15, matches * 5) # 5 pts por palavra-chave encontrada até 15
        
        return min(30, score)

    def _evaluate_engagement(self, count: int, text: str) -> int:
        """Avalia engajamento na conversa (Max 25 pts)"""
        score = 0
        
        # Quantidade de mensagens
        if count >= 2: # Relaxed from 3
            score += 5
        if count >= 4: # Relaxed from 6
            score += 5
            
        # Perguntas de retorno ou interesse
        interest_keywords = ["como funciona", "explique", "pode", "consegue", "reunião", "agendar", "marcar", "briefing"]
        if any(w in text for w in interest_keywords):
            score += 15
            
        return min(25, score)

    def _classify_score(self, score: int) -> str:
        if score >= 60:
            return "HOT"
        elif score >= 30:
            return "WARM"
        return "COLD"
