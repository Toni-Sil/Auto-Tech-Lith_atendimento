"""
Calendar Service with Smart Optimization
Antigravity Skill: business-logic
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, time
from app.infrastructure.database.supabase_client import SupabaseClient
from app.utils.logger import get_logger

logger = get_logger(__name__)

class CalendarService:
    def __init__(self):
        self.supabase = SupabaseClient.get_client()
        # Configuration
        self.start_hour = 9
        self.end_hour = 18
        self.slot_duration = 30 # minutes
        self.timezone_offset = -3 # Brasilia (UTC-3) - Simplified for now

    async def get_available_slots(self, date_str: str) -> Dict[str, Any]:
        """
        Returns available slots for a given date, ranked by 'smart score'.
        date_str format: YYYY-MM-DD
        """
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            
            # 1. Fetch existing appointments
            # Filter by date range (start of day to end of day)
            start_dt = f"{date_str}T00:00:00"
            end_dt = f"{date_str}T23:59:59"
            
            response = self.supabase.table("agendamentos").select("*") \
                .gte("data_hora", start_dt) \
                .lte("data_hora", end_dt) \
                .neq("status", "cancelado") \
                .execute()
                
            busy_times = []
            if response.data:
                for apt in response.data:
                    # Parse timestamp (assuming ISO format)
                    # DB stores timezone aware, we need to handle that.
                    # For MVP simplistic string comparison or naive datetime extraction
                    dt = datetime.fromisoformat(apt["data_hora"].replace("Z", "+00:00"))
                    # Convert to local time if needed, or assume input date_str is local
                    # For now extracting HH:MM from the ISO string directly might be safer if stored uniformly
                    # But let's use time object
                    busy_times.append(dt.time()) 

            # 2. Generate Candidate Slots
            candidates = []
            current_time = time(self.start_hour, 0)
            end_time = time(self.end_hour, 0)
            
            while current_time < end_time:
                # Check conflict
                is_busy = False
                # Simple conflict check: exact match (can look for overlaps later)
                # Ideally, we check ranges. 
                # For MVP: assume all slots start at :00 or :30 and last 30m.
                # If an appointment is at 10:00 (duration 30), 10:00 is busy.
                # If appointment is at 10:00 (duration 60), 10:00 and 10:30 are busy.
                
                # We need smarter conflict logic.
                # TODO: Improve conflict check for varying durations.
                # Current MVP: Check against start times found in DB (assuming 30m grid)
                
                for busy in busy_times:
                    # Naive match
                    if busy.hour == current_time.hour and busy.minute == current_time.minute:
                        is_busy = True
                        break
                
                if not is_busy:
                    score = self._calculate_score(target_date, current_time)
                    candidates.append({
                        "time": current_time.strftime("%H:%M"),
                        "score": score
                    })
                
                # Increment 30 mins
                dt = datetime.combine(target_date, current_time) + timedelta(minutes=self.slot_duration)
                current_time = dt.time()

            # 3. Rank Slots
            # Sort by score descending
            candidates.sort(key=lambda x: x["score"], reverse=True)
            
            return {
                "date": date_str,
                "total_slots": len(candidates),
                "recommended": candidates[:3], # Top 3
                "all_slots": [c["time"] for c in candidates]
            }

        except Exception as e:
            logger.error(f"Error getting availability: {e}")
            return {"error": str(e)}

    def _calculate_score(self, date_obj, time_obj) -> float:
        """
        Calculates productivity score for a slot.
        """
        score = 100.0
        
        # Day of Week (0=Mon, 6=Sun)
        weekday = date_obj.weekday()
        
        if weekday == 0: # Monday
            score -= 10
        elif weekday in [1, 2, 3]: # Tue, Wed, Thu
            score += 20
        elif weekday == 4: # Friday
            score -= 20
        elif weekday >= 5: # Weekend
            score -= 50
            
        # Time of Day
        hour = time_obj.hour
        
        if 14 <= hour < 16: # PM Focus Block (14-16)
            score += 30
        elif 9 <= hour < 12: # Morning
            score += 0 # Neutral
        elif hour >= 16: # Late afternoon
            score -= 10
            
        return score

    async def schedule_meeting(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Saves appointment to DB.
        """
        try:
            # Construct ISO timestamp
            # Input data["datetime"] should be ISO or "YYYY-MM-DD HH:MM"
            # Let's assume input is full ISO from the tool, or we construct it
            
            # Simple validation if needed
            
            payload = {
                "telefone_cliente": data.get("phone"),
                "nome_cliente": data.get("name"), # Might need to fetch name if not passed
                "tipo_reuniao": data.get("type", "briefing"),
                "data_hora": data.get("datetime"),
                "duracao_minutos": data.get("duration", 30),
                "status": "confirmado",
                "atendente": "MAX"
            }
            
            res = self.supabase.table("agendamentos").insert(payload).execute()
            if res.data:
                return {"status": "success", "data": res.data[0]}
                
            return {"status": "error", "message": "Falha ao salvar no banco"}
            
        except Exception as e:
            logger.error(f"Error scheduling meeting: {e}")
            return {"status": "error", "message": f"Erro interno: {str(e)}"}

    async def confirm_appointment(self, phone: str) -> Dict[str, Any]:
        """
        Confirms the next pending appointment for the client.
        """
        try:
            # Find next pending/scheduled appointment
            now = datetime.now().isoformat()
            res = self.supabase.table("agendamentos")\
                .select("*")\
                .eq("telefone_cliente", phone)\
                .gte("data_hora", now)\
                .eq("confirm_status", "pending")\
                .order("data_hora")\
                .limit(1)\
                .execute()
                
            if not res.data:
                return {"status": "error", "message": "Nenhum agendamento pendente encontrado para confirmação."}
                
            appt = res.data[0]
            
            # Update status
            self.supabase.table("agendamentos")\
                .update({"confirm_status": "confirmed"})\
                .eq("id", appt["id"])\
                .execute()
                
            return {
                "status": "success", 
                "message": f"Agendamento de {appt['nome_cliente']} em {appt['data_hora']} confirmado com sucesso!",
                "appointment": appt
            }
        except Exception as e:
            logger.error(f"Error confirming appointment: {e}")
            return {"status": "error", "message": str(e)}
