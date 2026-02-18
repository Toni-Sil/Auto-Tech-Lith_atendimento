"""
Core AI Service for MAX Agent
Antigravity Skill: agent-design
"""
import json
from typing import Optional, List, Dict, Any
import logging
from datetime import datetime

from app.config.settings import get_settings
from app.utils.logger import get_logger
from app.services.sentiment_service import SentimentService
from app.infrastructure.database.supabase_client import SupabaseClient
from app.core.scoring import LeadScorer
from app.services.notification_service import NotificationService
from openai import AsyncOpenAI

logger = get_logger(__name__)
settings = get_settings()

class AIService:
    def __init__(self):
        self.sentiment_service = SentimentService()
        self.supabase = SupabaseClient.get_client()
        self.openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model
        self.scorer = LeadScorer()
        self.notifier = NotificationService()
        
        # Load System Prompt
        try:
            with open("p:/agentes/dify/agent-prompt.md", "r", encoding="utf-8") as f:
                self.base_system_prompt = f.read()
        except Exception:
            # Fallback if file not found
            self.base_system_prompt = "Você é MAX, assistente virtual da Auto Tech Lith."

    async def _get_or_create_client(self, phone: str, name: Optional[str] = None):
        """Fetches client by phone, or creates a basic record if new."""
        try:
            response = self.supabase.table("dados cliente").select("*").eq("telefoneCliente", phone).execute()
            if response.data:
                return response.data[0]
            
            # Create new if name is provided (or just return None/empty to prompt for name)
            if name:
                new_client = {
                    "telefoneCliente": phone,
                    "nomeCliente": name,
                    "lead_score": 0,
                    "sentiment_history": []
                }
                res = self.supabase.table("dados cliente").insert(new_client).execute()
                if res.data:
                    return res.data[0]
            return None
        except Exception as e:
            logger.error(f"Error fetching/creating client: {e}")
            return None

    async def _update_sentiment_data(self, client_id: int, sentiment: Dict[str, Any]):
        """Updates client record with new sentiment score and history."""
        try:
            # Append to history (simplified here, ideally would fetch->append->update or use a stored procedure)
            # Fetch current history first to be safe, or assume the client obj has it
            
            # For efficiency in this MVP, we might just push to the array if Supabase supports it, 
            # but standard update is safer.
            
            current = self.supabase.table("dados cliente").select("sentiment_history").eq("id", client_id).execute()
            history = current.data[0].get("sentiment_history", []) if current.data else []
            if not isinstance(history, list):
                history = []
                
            new_entry = {
                "timestamp": datetime.now().isoformat(),
                "score": sentiment["score"],
                "label": sentiment["label"],
                "reasoning": sentiment.get("reasoning", "")
            }
            history.append(new_entry)
            
            self.supabase.table("dados cliente").update({
                "last_sentiment_score": sentiment["score"],
                "sentiment_history": history
            }).eq("id", client_id).execute()
            
        except Exception as e:
            logger.error(f"Error updating sentiment data: {e}")

    async def _update_lead_score(self, client_id: int, client_data: dict, current_message: str):
        """Calculates and updates lead score."""
        try:
            # Context construction
            # TODO: Fetch real interaction count from DB
            context = {
                "history": current_message, # Ideally would be full history
                "niche": client_data.get("nicho_trabalho", ""),
                "interaction_count": 1 # Placeholder
            }
            
            score_data = self.scorer.calculate_score(context)
            
            # Update DB
            self.supabase.table("dados cliente").update({
                "lead_score": score_data["total_score"],
                "score_breakdown": score_data["breakdown"]
            }).eq("id", client_id).execute()
            
            # Check for Hot Lead Alert (>= 75)
            # Only alert if score changed significantly or is new high? 
            # For now, alert every time it crosses threshold to be safe, 
            # but maybe limit to avoid spam. Simple logic: just alert.
            if score_data["total_score"] >= 60:
                # We interpret this as a "Hot Lead" event
                await self.notifier.send_lead_alert(client_data, score_data)
                
        except Exception as e:
            logger.error(f"Error updating lead score: {e}")

    async def process_message(self, message: str, sender_phone: str, sender_name: Optional[str] = None) -> str:
        """
        Main pipeline:
        1. Analyze Sentiment
        2. Retrieve/Update Client Context
        3. Build Dynamic Prompt
        4. Generate Response (with Tool Calling)
        """
        logger.info(f"Processing message from {sender_phone}: {message}")
        
        # 1. Analyze Sentiment
        sentiment = await self.sentiment_service.analyze_sentiment(message)
        
        # 2. Client Context
        # Use ClientService to find/create (refactoring old logic)
        # For now, keeping lightweight check here or moving entirely to ClientService?
        # Let's keep the existing _get_or_create_client logic for basic context, 
        # but the tool `register_client` will handle the deep update/validation.
        client = await self._get_or_create_client(sender_phone, sender_name)
        client_id = client.get("id") if client else None
        
        if client_id:
            await self._update_sentiment_data(client_id, sentiment)
            await self._update_lead_score(client_id, client, message)
        
        # 3. Dynamic Prompt Injection
        # ... (Existing prompt logic) ...
        system_prompt = self.base_system_prompt
        client_name = client.get("nomeCliente", "Visitante") if client else "Visitante"
        client_niche = client.get("nicho_trabalho", "Nicho não informado") if client else "Nicho não informado"
        system_prompt = system_prompt.replace("{{NICHE_CONTEXT}}", f"O cliente atua no nicho: {client_niche}.")
        
        # Tone Logic
        tone_instruction = ""
        if sentiment["score"] <= -0.5:
             tone_instruction = """
            🚨 **ALERTA DE SENTIMENTO NEGATIVO** 🚨
            O cliente parece frustrado ou insatisfeito.
            - Peça desculpas sinceramente por qualquer inconveniente.
            - Seja extremamente empático e paciente.
            - Evite respostas genéricas ou robóticas.
            - Pergunte como você pode resolver o problema IMEDIATAMENTE.
            """
             # Notify Team logic
             notification_msg = f"Sentiment Alert: Client {sender_phone} is FRUSTRATED.\nScore: {sentiment['score']}\nMessage: {message}"
             try:
                 await self.notifier.send_alert(notification_msg, level="CRITICAL")
             except Exception as e:
                 logger.error(f"Failed to trigger notification: {e}")
                 
        elif sentiment["score"] >= 0.7:
             tone_instruction = """
            🌟 **ALERTA DE SENTIMENTO POSITIVO** 🌟
            O cliente está satisfeito e engajado.
            - Aproveite para reforçar a autoridade da Auto Tech Lith.
            - Seja confiante e proativo para fechar a reunião/venda.
            - Se apropriado, sugira um próximo passo claro (ex: agendar briefing agora).
            """
        else:
            tone_instruction = "Mantenha um tone profissional, prestativo e neutro/positivo."
            
        system_prompt = system_prompt.replace("{{TONE_INSTRUCTIONS}}", tone_instruction)
        
        # 4. Generate Response with Tools
        from app.core.tools import TOOLS_SCHEMA
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message}
        ]
        
        try:
            # First Call: See if model wants to use a tool
            response = await self.openai_client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto",
                temperature=0.7
            )
            
            msg = response.choices[0].message
            tool_calls = msg.tool_calls
            
            if tool_calls:
                # Append the model's request to messages
                messages.append(msg)
                
                # Execute tools
                for tool_call in tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)
                    
                    logger.info(f"Executing tool {function_name} with args {function_args}")
                    
                    tool_output = f"Error: Tool {function_name} not found"
                    
                    if function_name == "registrar_cliente":
                         from app.services.client_service import ClientService
                         svc = ClientService()
                         # Ensure phone is passed if missing (using sender_phone)
                         if "phone" not in function_args:
                             function_args["phone"] = sender_phone
                             
                         result = await svc.register_client(function_args)
                         tool_output = json.dumps(result)
                         
                    elif function_name == "horarios_disponiveis":
                        from app.services.calendar_service import CalendarService
                        calendar_svc = CalendarService()
                        
                        date_str = function_args.get("date")
                        if not date_str:
                             date_str = datetime.now().strftime("%Y-%m-%d")
                             
                        result = await calendar_svc.get_available_slots(date_str)
                        tool_output = json.dumps(result)
                        
                    elif function_name == "agendar_reuniao":
                        from app.services.calendar_service import CalendarService
                        calendar_svc = CalendarService()
                        
                        if "phone" not in function_args:
                            function_args["phone"] = sender_phone
                            
                        # If name missing, try to get from context if possible
                        if "name" not in function_args and client:
                             function_args["name"] = client.get("nomeCliente")

                        # Call CalendarService
                        result = await calendar_svc.schedule_meeting(function_args)
                        
                        # Add follow-up logic explanation to tool output if successful
                        if result.get("status") == "success":
                             # (Optional) Trigger follow-up tasks here if needed
                             pass
                             
                        tool_output = json.dumps(result)

                    elif function_name == "confirmar_agendamento":
                        from app.services.calendar_service import CalendarService
                        calendar_svc = CalendarService()
                        
                        # Phone from args or context
                        phone = function_args.get("phone", sender_phone)
                        
                        result = await calendar_svc.confirm_appointment(phone)
                        tool_output = json.dumps(result)

                    # Add tool result to messages
                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": tool_output
                    })
                
                # Second Call: Get final text response
                final_response = await self.openai_client.chat.completions.create(
                    model=self.model,
                    messages=messages
                )
                response_text = final_response.choices[0].message.content
                
                # SEND THE MESSAGE
                await self.notifier.send_whatsapp_message(sender_phone, response_text)
                return response_text
            
            # If no tool calls, just return and send
            await self.notifier.send_whatsapp_message(sender_phone, msg.content)
            return msg.content
            
        except Exception as e:
            logger.error(f"Error generating AI response: {e}")
            error_msg = "Desculpe, tive um erro interno. Pode repetir?"
            # Fallback attempt to send error message
            await self.notifier.send_whatsapp_message(sender_phone, error_msg)
            return error_msg

    async def transcribe_audio(self, audio_content: bytes) -> str:
        """Transcribes audio using OpenAI Whisper."""
        try:
            # Whisper expects a file-like object or path
            # For simplicity, we can use a temporary file or just pass it if the SDK allows
            # The AsyncOpenAI client has a specific method for this.
            # We'll save to a temp file for Whisper to process
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
                tmp.write(audio_content)
                tmp_path = tmp.name
                
            try:
                with open(tmp_path, "rb") as audio_file:
                    logger.info(f"Sending audio to Whisper: {tmp_path} ({len(audio_content)} bytes)")
                    transcript = await self.openai_client.audio.transcriptions.create(
                        model=settings.openai_whisper_model,
                        file=("audio.ogg", audio_file)
                    )
                return transcript.text
            finally:
                import os
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                    
        except Exception as e:
            logger.error(f"Audio transcription failed: {e}")
            with open("audio_pipeline.log", "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now()}] Transcription ERROR: {str(e)}\n")
            return ""
