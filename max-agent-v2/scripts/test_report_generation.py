import sys
import os

# Adiciona diretório raiz no path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.report_service import ReportService
from app.services.analytics_service import AnalyticsService

def test_report():
    print("=== TESTANDO GERAÇÃO DE RELATÓRIO PDF ===\n")
    
    analytics_service = AnalyticsService()
    report_service = ReportService()
    
    # 1. Fetch Metrics
    metrics = analytics_service.get_funnel_metrics(days=30)
    print("Metrics fetched.")
    
    # 2. Generate Insights
    insights = analytics_service.generate_insights(metrics)
    print("Insights generated.")
    
    # 3. Generate Report
    try:
        filepath = report_service.generate_funnel_report(metrics, insights)
        print(f"✅ Relatório gerado com sucesso em: {filepath}")
        
        # Check if file exists
        if os.path.exists(filepath):
             print(f"Arquivo verificado no disco: {os.path.abspath(filepath)}")
        else:
             print("❌ Erro: Arquivo não encontrado após geração.")
             
    except Exception as e:
        print(f"❌ Erro ao gerar relatório: {e}")

if __name__ == "__main__":
    test_report()
