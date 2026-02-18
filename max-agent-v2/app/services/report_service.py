from fpdf import FPDF  # type: ignore
from datetime import datetime
import os
from app.utils.logger import get_logger

logger = get_logger(__name__)

class ReportService:
    def __init__(self):
        self.output_dir = "reports"
        os.makedirs(self.output_dir, exist_ok=True)

    def generate_funnel_report(self, metrics: dict, insights: list) -> str:
        """
        Generates a PDF report for the sales funnel analysis.
        Returns the path to the generated file.
        """
        try:
            # Explicitly set A4 and mm units
            pdf = FPDF(orientation='P', unit='mm', format='A4')
            pdf.add_page()
            
            # Helper to sanitize text for Latin-1 (Standard FPDF fonts)
            def sanitize(text):
                return str(text).encode('latin-1', 'replace').decode('latin-1')

            # Title
            pdf.set_font("Helvetica", "B", 16)
            pdf.cell(0, 10, sanitize("Simetria - Relatório de Funil de Vendas"), ln=True, align='C')
            
            # Subtitle / Date
            pdf.set_font("Helvetica", "", 12)
            current_date = datetime.now().strftime("%d/%m/%Y")
            pdf.cell(0, 10, sanitize(f"Gerado em: {current_date}"), ln=True, align='C')
            pdf.ln(10)
            
            # --- Funnel Overview ---
            pdf.set_font("Helvetica", "B", 14)
            pdf.cell(0, 10, sanitize("Visão Geral do Funil (30 Dias)"), ln=True)
            pdf.ln(5)
            
            counts = metrics.get("counts", {})
            rates = metrics.get("rates", {})
            
            # Table Header
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_fill_color(240, 240, 240)
            # Reduced width to 160mm total (safe for A4 which is 210mm)
            pdf.cell(60, 10, sanitize("Etapa"), border=1, fill=True)
            pdf.cell(50, 10, sanitize("Quantidade"), border=1, fill=True)
            pdf.cell(50, 10, sanitize("Conversão Etapa"), border=1, fill=True)
            pdf.ln()
            
            # Table Rows
            pdf.set_font("Helvetica", "", 10)
            
            stages = [
                ("Leads Totais", counts.get("leads"), "-"),
                ("Qualificados", counts.get("qualified"), f"{rates.get('lead_to_qualified')}%"),
                ("Agendados", counts.get("booked"), f"{rates.get('qualified_to_booked')}%"),
                ("Compareceram (Show)", counts.get("showed"), f"{rates.get('booked_to_showed')}%"),
                ("Propostas Enviadas", counts.get("proposed"), f"{rates.get('showed_to_proposed')}%"),
                ("Fechados (Venda)", counts.get("closed"), f"{rates.get('proposed_to_closed')}%")
            ]
            
            for stage, count, rate in stages:
                pdf.cell(60, 10, sanitize(stage), border=1)
                pdf.cell(50, 10, sanitize(str(count)), border=1)
                pdf.cell(50, 10, sanitize(rate), border=1)
                pdf.ln()
                
            pdf.ln(5)
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(0, 10, sanitize(f"Conversão Global: {rates.get('overall')}%"), ln=True)
            pdf.ln(10)
            
            # --- Insights ---
            pdf.set_font("Helvetica", "B", 14)
            pdf.cell(0, 10, sanitize("Insights & Ações Recomendadas"), ln=True)
            pdf.ln(5)
            
            pdf.set_font("Helvetica", "", 11)
            for insight in insights:
                # Clean emoji characters as FPDF standard fonts don't support them well
                clean_insight = insight.replace("⚠️", "[ATENCAO] ").replace("❌", "[CRITICO] ").replace("✅", "[OK] ")
                # Use explicit width to avoid auto-calc issues (A4 width 210 - margins 20 = 190, use 180 safely)
                pdf.multi_cell(180, 8, sanitize(f"- {clean_insight}"))
                
            # --- Footer ---
            filename = f"funnel_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            filepath = os.path.join(self.output_dir, filename)
            pdf.output(filepath)
            
            logger.info(f"Report generated: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Failed to generate report: {e}")
            raise
