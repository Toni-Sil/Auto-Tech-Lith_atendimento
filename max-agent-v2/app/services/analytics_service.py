from app.infrastructure.database.supabase_client import SupabaseClient
from app.utils.logger import get_logger
from datetime import datetime, timedelta

logger = get_logger(__name__)

class AnalyticsService:
    def __init__(self):
        self.supabase = SupabaseClient.get_client()

    def get_funnel_metrics(self, days: int = 30):
        """
        Calculates funnel metrics for the last N days.
        """
        try:
            # We can't easily do complex SQL with the JS client wrapper in Python 
            # without rpc or raw sql if exposed. 
            # For now, fetching all relevant fields and aggregating in Python 
            # is safer and easier given the library constraints, 
            # unless we have a massive DB (which we likely don't yet).
            
            # Date limit calculation
            date_limit = datetime.now() - timedelta(days=days)
            
            # Fetch data (Optimized select)
            response = self.supabase.table("customers").select(
                "id, created_at, lead_score, funnel_stage, status_briefing, status_proposta, data_briefing, data_proposta"
            ).execute()
            
            data = response.data if response.data else []
            
            metrics = {
                "leads": 0,
                "qualified": 0,
                "booked": 0,
                "showed": 0,
                "proposed": 0,
                "closed": 0
            }
            
            for lead in data:
                # Filter by date
                created_at_str = lead.get("created_at")
                if created_at_str:
                    try:
                        # Handle potential timezone 'Z' or offset
                        created_dt = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                        # Remove timezone info for comparison if local time is naive, or make both aware
                        # Assuming date_limit is naive local, let's make created_dt naive or convert limit
                        if created_dt.replace(tzinfo=None) < date_limit:
                            continue
                    except ValueError:
                        pass # Skip date check if format is weird, or just include it? Better to include recent ones.
                
                metrics["leads"] += 1
                
                # Qualified (Score >= 50)
                score = lead.get("lead_score", 0)
                try:
                    score = int(score)
                except (ValueError, TypeError):
                    score = 0
                    
                if score >= 50:
                    metrics["qualified"] += 1
                    
                # Booked
                stage = lead.get("funnel_stage")
                data_briefing = lead.get("data_briefing")
                if data_briefing or stage in ['agendado', 'briefing', 'proposta', 'fechado']:
                    metrics["booked"] += 1
                    
                # Showed
                status_briefing = lead.get("status_briefing")
                if status_briefing == 'realizado':
                    metrics["showed"] += 1
                    
                # Proposed
                status_proposta = lead.get("status_proposta")
                data_proposta = lead.get("data_proposta")
                if data_proposta or status_proposta in ['enviada', 'aceita'] or stage in ['proposta', 'fechado']:
                    metrics["proposed"] += 1
                    
                # Closed
                if status_proposta == 'aceita' or stage == 'fechado':
                    metrics["closed"] += 1
            
            # Calculate Conversions
            conversions = {
                "lead_to_qualified": self._safe_div(metrics["qualified"], metrics["leads"]),
                "qualified_to_booked": self._safe_div(metrics["booked"], metrics["qualified"]),
                "booked_to_showed": self._safe_div(metrics["showed"], metrics["booked"]),
                "showed_to_proposed": self._safe_div(metrics["proposed"], metrics["showed"]),
                "proposed_to_closed": self._safe_div(metrics["closed"], metrics["proposed"]),
                "overall": self._safe_div(metrics["closed"], metrics["leads"])
            }
            
            return {
                "counts": metrics,
                "rates": conversions
            }
            
        except Exception as e:
            logger.error(f"Error fetching funnel metrics: {e}")
            return {}

    def _safe_div(self, a, b):
        if b == 0: return 0
        return round((a / b) * 100, 1)

    def generate_insights(self, metrics: dict):
        """Generates text insights based on metrics."""
        insights = []
        counts = metrics.get("counts", {})
        rates = metrics.get("rates", {})
        
        if rates.get("qualified_to_booked", 0) < 30:
            insights.append("⚠️ Baixa conversão em Agendamento (<30%). Verifique se o agente está ofertando horários corretamente.")
            
        if rates.get("booked_to_showed", 0) < 70:
            insights.append("⚠️ Taxa de No-Show alta (>30%). Reforce os lembretes de WhatsApp (Implementação #5).")
            
        if rates.get("proposed_to_closed", 0) < 20:
             insights.append("❌ Fechamento baixo (<20%). Preço ou Proposta podem não estar alinhados.")
             
        if not insights:
            insights.append("✅ Funil saudável. Continue monitorando.")
            
        return insights
