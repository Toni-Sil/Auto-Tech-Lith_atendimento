import sys
import os

# Adiciona diretório raiz no path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.analytics_service import AnalyticsService

def test_funnel():
    print("=== TESTANDO FUNIL DE VENDAS ===\n")
    
    service = AnalyticsService()
    
    # Executa análise (vai pegar dados reais do Supabase, que podem ser poucos agora)
    # Idealmente, teríamos um mock, mas vamos rodar para ver se não quebra com dados vazios/reais
    results = service.get_funnel_metrics(days=30)
    
    counts = results.get("counts", {})
    rates = results.get("rates", {})
    
    print("🔢 CONTAGENS:")
    print(f"Leads: {counts.get('leads')}")
    print(f"Qualificados: {counts.get('qualified')}")
    print(f"Agendados: {counts.get('booked')}")
    print(f"Compareceram: {counts.get('showed')}")
    print(f"Propostas: {counts.get('proposed')}")
    print(f"Fechados: {counts.get('closed')}")
    
    print("\n📉 TAXAS DE CONVERSÃO:")
    print(f"Lead -> Qualificado: {rates.get('lead_to_qualified')}%")
    print(f"Qualificado -> Agendado: {rates.get('qualified_to_booked')}%")
    print(f"Agendado -> Show: {rates.get('booked_to_showed')}%")
    print(f"Show -> Proposta: {rates.get('showed_to_proposed')}%")
    print(f"Proposta -> Fechado: {rates.get('proposed_to_closed')}%")
    print(f"Global (Lead -> Closed): {rates.get('overall')}%")
    
    print("\n💡 INSIGHTS:")
    insights = service.generate_insights(results)
    for i in insights:
        print(i)

if __name__ == "__main__":
    test_funnel()
