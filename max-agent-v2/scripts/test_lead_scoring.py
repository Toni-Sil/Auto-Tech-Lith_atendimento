import sys
import os

# Adiciona diretório raiz no path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.scoring import LeadScorer

def run_tests():
    scorer = LeadScorer()
    
    scenarios = [
        {
            "name": "Lead Quente (Orçamento + Urgência + Fit)",
            "context": {
                "history": "Olá, preciso urgente de um bot de atendimento. Qual o orçamento para implantar essa semana? Tenho dinheiro pra investir.",
                "niche": "clinica_estetica",
                "interaction_count": 5
            },
            "expected_classification": "HOT"
        },
        {
            "name": "Lead Morno (Curioso, sem pressa)",
            "context": {
                "history": "Oi, queria saber como funciona. Vocês fazem site?",
                "niche": "advocacia",
                "interaction_count": 2
            },
            "expected_classification": "WARM" # ou COLD, vamos ver
        },
        {
            "name": "Lead Frio (Sem contexto, frase curta)",
            "context": {
                "history": "bom dia",
                "niche": "",
                "interaction_count": 1
            },
            "expected_classification": "COLD"
        },
        {
            "name": "Cliente com Dor Específica (Fit Alto)",
            "context": {
                "history": "Estou perdendo muito cliente por demora no atendimento. Ninguém responde no almoço. Preciso automatizar agendamento.",
                "niche": "restaurante",
                "interaction_count": 4
            },
            "expected_classification": "HOT" # ou WARM high
        }
    ]
    
    print("=== TESTANDO LEAD SCORING ===\n")
    
    for s in scenarios:
        print(f"--- {s['name']} ---")
        result = scorer.calculate_score(s["context"])
        
        score = result["total_score"]
        classification = result["classification"]
        breakdown = result["breakdown"]
        
        print(f"Score Total: {score} ({classification})")
        print(f"Breakdown: {breakdown}")
        
        # Validação simples
        if classification == s.get("expected_classification") or (score >= 50 and s.get("expected_classification") == "WARM"):
            print("✅ Resultado Esperado")
        else:
            print(f"⚠️ Resultado Divergente (Esperado: {s.get('expected_classification')})")
            
        print("\n")

if __name__ == "__main__":
    run_tests()
