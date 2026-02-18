from fpdf import FPDF
import os

def debug_pdf():
    print("=== DEBUGGING PDF GENERATION ===")
    try:
        pdf = FPDF(orientation='P', unit='mm', format='A4')
        pdf.add_page()
        print("Page added.")
        
        # Helper to sanitize text for Latin-1 (Standard FPDF fonts)
        def sanitize(text):
            return str(text).encode('latin-1', 'replace').decode('latin-1')

        # Title
        print("Adding Title...")
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(0, 10, sanitize("Simetria - Relatório de Funil de Vendas"), ln=True, align='C')
        
        # Subtitle / Date
        print("Adding Subtitle...")
        pdf.set_font("Helvetica", "", 12)
        pdf.cell(0, 10, sanitize(f"Gerado em: 13/02/2026"), ln=True, align='C')
        pdf.ln(10)
        
        # --- Funnel Overview ---
        print("Adding Overview Header...")
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10, sanitize("Visão Geral do Funil (30 Dias)"), ln=True)
        pdf.ln(5)
        
        # Table Header
        print("Adding Table Header...")
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_fill_color(240, 240, 240)
        pdf.cell(70, 10, sanitize("Etapa"), border=1, fill=True)
        pdf.cell(60, 10, sanitize("Quantidade"), border=1, fill=True)
        pdf.cell(60, 10, sanitize("Conversão Etapa"), border=1, fill=True)
        pdf.ln()
        
        print("Adding Table Rows...")
        # Table Rows
        pdf.set_font("Helvetica", "", 10)
        
        stages = [
            ("Leads Totais", 5, "-"),
            ("Qualificados", 0, "0.0%"),
            ("Agendados", 0, "0.0%"),
            ("Compareceram (Show)", 0, "0.0%"),
            ("Propostas Enviadas", 0, "0.0%"),
            ("Fechados (Venda)", 0, "0.0%")
        ]
        
        for stage, count, rate in stages:
            pdf.cell(70, 10, sanitize(stage), border=1)
            pdf.cell(60, 10, sanitize(str(count)), border=1)
            pdf.cell(60, 10, sanitize(rate), border=1)
            pdf.ln()
            
        pdf.ln(5)
        print("Adding Summary...")
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 10, sanitize(f"Conversão Global: 0.0%"), ln=True)
        pdf.ln(10)
        
        # --- Insights ---
        print("Adding Insights Header...")
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10, sanitize("Insights & Ações Recomendadas"), ln=True)
        pdf.ln(5)
        
        print("Adding Insights Body...")
        pdf.set_font("Helvetica", "", 11)
        insights = [
            "⚠️ Baixa conversão em Agendamento (<30%). Verifique se o agente está ofertando horários corretamente.",
            "⚠️ Taxa de No-Show alta (>30%). Reforce os lembretes de WhatsApp (Implementação #5).",
            "❌ Fechamento baixo (<20%). Preço ou Proposta podem não estar alinhados."
        ]
        for insight in insights:
            clean_insight = insight.replace("⚠️", "[ATENCAO] ").replace("❌", "[CRITICO] ").replace("✅", "[OK] ")
            # Use explicit width to avoid auto-calc issues (A4 width 210 - margins 20 = 190, use 180 safely)
            pdf.multi_cell(180, 8, sanitize(f"- {clean_insight}"))
            
        filename = "debug_report_v2.pdf"
        pdf.output(filename)
        print(f"PDF saved to {filename}")
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_pdf()
