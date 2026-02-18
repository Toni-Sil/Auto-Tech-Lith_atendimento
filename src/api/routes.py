from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import Annotated
from src.api.auth import get_current_user, AdminUser
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, or_
from typing import List
from datetime import datetime, date

from src.models.database import get_db
from src.models.customer import Customer
from src.models.ticket import Ticket, TicketStatus
from src.models.meeting import Meeting, MeetingStatus, MeetingType
from src.models.conversation import Conversation
from src.schemas import (
    CustomerCreate, CustomerResponse,
    MeetingCreate, MeetingResponse,
    TicketCreate, TicketResponse,
    DashboardStats, WebhookPayload,
    ConversationResponse, ChatTestRequest
)
from src.agents.customer_service_agent import customer_agent
from src.services.evolution_service import evolution_service
from src.services.llm_service import llm_service
from src.services.audio_service import AudioService
from src.services.audio_service import audio_service
from src.services.analytics_service import analytics_service
from src.utils.logger import setup_logger
import base64
import tempfile
import os

from src.models.config_model import SystemConfig
from src.config import settings

logger = setup_logger(__name__)
api_router = APIRouter()

# --- Configuration ---
@api_router.get("/config")
@api_router.get("/config")
async def get_config(
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(SystemConfig))
    configs = result.scalars().all()
    
    # Mask secrets
    response = []
    for c in configs:
        val = c.value
        if c.is_secret and val:
            val = "********"
        response.append({"key": c.key, "value": val, "description": c.description})
    return response

@api_router.post("/config")
@api_router.post("/config")
async def update_config(
    payload: dict, 
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    # payload: {"key": "value"}
    for key, value in payload.items():
        # Check if exists
        config = await db.scalar(select(SystemConfig).where(SystemConfig.key == key))
        if config:
            config.value = value
            # If logic needed to reload services, could trigger here
        else:
            # Auto-create if not exists (careful with secrets)
            # Defaulting is_secret to False for new keys via API for now
            new_config = SystemConfig(key=key, value=value, is_secret=False)
            db.add(new_config)
            
    await db.commit()
    return {"status": "updated"}

# --- Dashboard Stats ---
@api_router.get("/stats", response_model=DashboardStats)
@api_router.get("/stats", response_model=DashboardStats)
async def get_stats(
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    # Estatísticas básicas
    active_customers = await db.scalar(select(func.count(Customer.id)))
    # Tickets abertos
    open_tickets = await db.scalar(select(func.count(Ticket.id)).where(Ticket.status == TicketStatus.OPEN))
    # Reuniões agendadas
    scheduled_meetings = await db.scalar(select(func.count(Meeting.id)).where(
        Meeting.status == MeetingStatus.SCHEDULED,
        Meeting.date >= date.today()
    ))
    # Conversas de hoje
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_conversations = await db.scalar(select(func.count(Conversation.id)).where(Conversation.created_at >= today_start))

    return DashboardStats(
        active_customers=active_customers or 0,
        open_tickets=open_tickets or 0,
        scheduled_meetings=scheduled_meetings or 0,
        today_conversations=today_conversations or 0
    )

# --- Customers ---
@api_router.get("/customers", response_model=List[CustomerResponse])
async def list_customers(
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    # Query com contagem de tickets abertos
    stmt = (
        select(Customer, func.count(Ticket.id).label("open_tickets_count"))
        .outerjoin(Ticket, (Ticket.customer_id == Customer.id) & (Ticket.status == TicketStatus.OPEN))
        .group_by(Customer.id)
        .order_by(desc(Customer.last_interaction))
    )
    result = await db.execute(stmt)
    
    customers = []
    for customer, count in result:
        # Pydantic validates from ORM object, but we need to inject the count
        # or convert to dict. Since schema has from_attributes=True, 
        # we can attach the attribute ensuring it doesn't conflict with ORM state.
        # Safer approach: create model from dict/attributes
        c_dict = customer.__dict__.copy()
        c_dict['open_tickets_count'] = count
        customers.append(CustomerResponse.model_validate(c_dict))
        
    return customers

@api_router.post("/customers", response_model=CustomerResponse)
async def create_customer(
    customer: CustomerCreate, 
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    # Verificar duplicidade por telefone APENAS se não for update explícito
    # (Embora POST seja criação, mantemos a lógica de upsert por conveniência, 
    # mas o ideal é o frontend usar PUT para edição)
    existing = await db.scalar(select(Customer).where(Customer.phone == customer.phone))
    if existing:
        return existing # Retorna o existente sem alterar, ou atualiza? 
        # A lógica anterior atualizava. Vamos manter o POST como creation apenas ou upsert.
        # Melhor: POST cria. Se já existe, erro 400 ou retorna o existente.
        # Vamos manter comportamento "upsert" suave mas sem alterar dados para evitar overwrite acidental?
        # A regra de negócio anterior era: Se existe, ATUALIZA. OK.
        existing.name = customer.name
        existing.email = customer.email
        existing.company = customer.company
        existing.initial_demand = customer.initial_demand
        if customer.status:
            existing.status = customer.status
        existing.updated_at = datetime.now()
        await db.commit()
        await db.refresh(existing)
        return existing

    new_customer = Customer(**customer.model_dump())
    db.add(new_customer)
    await db.commit()
    await db.refresh(new_customer)
    return new_customer

@api_router.put("/customers/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: int, 
    customer_data: CustomerCreate, 
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    existing = await db.get(Customer, customer_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    existing.name = customer_data.name
    existing.phone = customer_data.phone
    existing.email = customer_data.email
    existing.company = customer_data.company
    existing.initial_demand = customer_data.initial_demand
    if customer_data.status:
        existing.status = customer_data.status
    existing.updated_at = datetime.now()
    
    await db.commit()
    await db.refresh(existing)
    return existing

@api_router.delete("/customers/{customer_id}")
async def delete_customer(
    customer_id: int, 
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    customer = await db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    await db.delete(customer)
    await db.commit()
    return {"status": "deleted"}

# --- Tickets ---
@api_router.get("/tickets", response_model=List[TicketResponse])
@api_router.get("/tickets", response_model=List[TicketResponse])
async def list_tickets(
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    # Join com Customer para pegar nome
    result = await db.execute(select(Ticket, Customer.name).join(Customer).order_by(desc(Ticket.created_at)))
    tickets = []
    for ticket, customer_name in result:
        t_resp = TicketResponse.model_validate(ticket)
        t_resp.customer_name = customer_name
        tickets.append(t_resp)
    return tickets

# --- Meetings ---
@api_router.get("/meetings", response_model=List[MeetingResponse])
@api_router.get("/meetings", response_model=List[MeetingResponse])
async def list_meetings(
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Meeting, Customer.name).join(Customer).order_by(Meeting.date, Meeting.time))
    meetings = []
    for meeting, customer_name in result:
        m_resp = MeetingResponse.model_validate(meeting)
        m_resp.customer_name = customer_name
        meetings.append(m_resp)
    return meetings

@api_router.post("/meetings", response_model=MeetingResponse)
@api_router.post("/meetings", response_model=MeetingResponse)
async def create_meeting(
    meeting: MeetingCreate, 
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    new_meeting = Meeting(**meeting.model_dump())
    db.add(new_meeting)
    
    # 2. Automate Customer Status Update
    customer = await db.get(Customer, new_meeting.customer_id)
    if customer:
        if new_meeting.type == MeetingType.BRIEFING:
            customer.status = "briefing"
        elif new_meeting.type == MeetingType.PROPOSAL:
            customer.status = "proposal"
        # Outros status (mensal, finalizado) são manuais
            
    await db.commit()
    await db.refresh(new_meeting)
    
    resp = MeetingResponse.model_validate(new_meeting)
    resp.customer_name = customer.name if customer else "Unknown"
    return resp

@api_router.put("/meetings/{meeting_id}", response_model=MeetingResponse)
@api_router.put("/meetings/{meeting_id}", response_model=MeetingResponse)
async def update_meeting(
    meeting_id: int, 
    meeting_data: MeetingCreate, 
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    existing = await db.get(Meeting, meeting_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Meeting not found")
    
    existing.date = meeting_data.date
    existing.time = meeting_data.time
    existing.type = meeting_data.type
    existing.notes = meeting_data.notes
    # existing.status = meeting_data.status # Se quisermos editar status tb
    
    await db.commit()
    await db.refresh(existing)
    
    customer = await db.get(Customer, existing.customer_id)
    resp = MeetingResponse.model_validate(existing)
    resp.customer_name = customer.name if customer else "Unknown"
    return resp

@api_router.delete("/meetings/{meeting_id}")
@api_router.delete("/meetings/{meeting_id}")
async def delete_meeting(
    meeting_id: int, 
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    
    await db.delete(meeting)
    await db.commit()
    return {"status": "deleted"}

# --- Webhooks ---
from fastapi import Request
@api_router.post("/webhooks/whatsapp")
async def whatsapp_webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse webhook JSON: {e}")
        return {"status": "error", "reason": "invalid json"}
        
    # Security: Verify Webhook Token
    # Check query param 'token' or header 'Verification-Token'
    token = request.query_params.get("token") or request.headers.get("verification-token")
    if token != settings.VERIFY_TOKEN:
        logger.warning(f"Unauthorized webhook attempt with token: {token}")
        raise HTTPException(status_code=403, detail="Invalid verification token")

    logger.info(f"Webhook received: {payload}")
    
    # Identificar mensagem de texto
    # Estrutura típica Evolution API v2:
    if not isinstance(payload, dict):
         logger.warning(f"Received non-dict payload: {type(payload)}")
         return {"status": "ignored", "reason": "payload is not a dict"}
         
    data = payload.get("data", {})
    
    # Validação de tipo: eventos como 'contacts.update' enviam lista em 'data'
    if not isinstance(data, dict):
        return {"status": "ignored", "reason": "data is not a dict (likely system event)"}

    message = data.get("message", {})
    
    if not message:
         # Tenta estrutura v1 ou diferente se necessario
         return {"status": "ignored", "reason": "no message data"}

    # Extrair dados
    # Remetente (remoteJid geralmente é o numero@s.whatsapp.net)
    key = data.get("key", {})
    remote_jid = key.get("remoteJid", "")
    from_me = key.get("fromMe", False)
    message_id = key.get("id", "")
    
    # Ignorar mensagens enviadas pelo próprio sistema (evitar loop)
    if from_me:
        return {"status": "ignored", "reason": "fromMe is true"}

    if remote_jid and message_id:
        # Marcar como lido imediatamente (visualização azul)
        background_tasks.add_task(evolution_service.mark_message_as_read, remote_jid, message_id)

    phone = remote_jid.split("@")[0] if remote_jid else ""
    
    # Texto
    text = message.get("conversation") or message.get("extendedTextMessage", {}).get("text")
    
    # Processar Áudio
    audio_message = message.get("audioMessage")
    if audio_message:
        message_id = data.get("key", {}).get("id")
        mimetype = audio_message.get("mimetype", "audio/ogg").split(";")[0] # ex: audio/ogg; codecs=opus -> audio/ogg
        
        # Mapear extensão
        import mimetypes
        extension = mimetypes.guess_extension(mimetype) or ".ogg"
        if extension == ".oga": extension = ".ogg" # Common fix
        
        logger.info(f"Audio message received ID: {message_id}, Mimetype: {mimetype}, Ext: {extension}")
        
        # Tentar obter base64 (payload ou fetch)
        media_base64 = audio_message.get("base64")
        if not media_base64:
            logger.info(f"Base64 not found in payload for msg {message_id}, fetching from API...")
            # We must pass the FULL data object (containing key, message, etc)
            media_base64 = await evolution_service.get_media_base64(data)
        else:
             logger.info(f"Base64 found directly in payload for msg {message_id}")
            
        if media_base64:
            temp_audio_path = None
            try:
                # Salvar arquivo temporário
                audio_data = base64.b64decode(media_base64)
                file_size = len(audio_data)
                logger.info(f"Decoded audio size: {file_size} bytes")
                
                with tempfile.NamedTemporaryFile(suffix=extension, delete=False) as temp_audio:
                    temp_audio.write(audio_data)
                    temp_audio_path = temp_audio.name
                
                logger.info(f"Audio saved to temp file: {temp_audio_path}")

                # Transcrever
                try:
                    # Usar AudioService local (Whisper + FFmpeg)
                    # Não precisa abrir o arquivo, passar o caminho direto
                    from src.services.audio_service import audio_service
                    
                    # Offload para thread pool se o método for síncrono (Whisper é bloqueante e cpu-bound)
                    # O AudioService.transcribe é síncrono.
                    import asyncio
                    from functools import partial
                    
                    loop = asyncio.get_running_loop()
                    transcription = await loop.run_in_executor(
                        None, 
                        partial(audio_service.transcribe, temp_audio_path)
                    )
                    
                    if transcription:
                        text = f"[Áudio]: {transcription}"
                        logger.info(f"Transcribed text: {text}")
                    else:
                        logger.warning(f"Transcription returned empty string for msg {message_id}")
                        # DUMP AUDIO FOR DEBUG
                        debug_dir = "debug_audio"
                        if not os.path.exists(debug_dir): os.makedirs(debug_dir)
                        debug_path = os.path.join(debug_dir, f"failed_{message_id}{extension}")
                        with open(debug_path, "wb") as f_debug:
                            f_debug.write(audio_data)
                        logger.info(f"Saved failed audio to {debug_path} for inspection")
                        
                except Exception as e:
                     logger.error(f"Error calling Whisper for msg {message_id}: {e}")
                finally:
                    # Limpar arquivo temporário
                    if temp_audio_path and os.path.exists(temp_audio_path):
                        os.unlink(temp_audio_path)
            except Exception as e:
                logger.error(f"Error processing audio content (decoding/file): {e}")
        else:
            logger.error(f"Failed to obtain media base64 for audio message {message_id}")
        
        # Fallback: Se falhou em obter texto (por erro no download ou transcrição),
        # definimos um texto padrão para o agente saber que houve uma tentativa de áudio.
        if not text:
             text = "[Áudio recebido, mas houve falha na transcrição. Peça para o usuário escrever.]"
             logger.warning(f"Audio processing failed for {message_id}. Using fallback text.")

    # Nome (pushName)
    push_name = data.get("pushName", "Cliente WhatsApp")
    
    if phone and text:
        # Processar em background para não bloquear o webhook
        background_tasks.add_task(
            customer_agent.process_message, 
            message=text, 
            context={"phone": phone, "name": push_name}
        )
        return {"status": "processing"}
    
    return {"status": "ignored", "reason": "invalid data"}

# --- Health ---
@api_router.get("/health/evolution")
async def health_evolution():
    status = await evolution_service.check_instance_status()
    if "error" in status:
        raise HTTPException(status_code=503, detail="Evolution API unreachable")
    return status

@api_router.get("/health/database")
async def health_database(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(select(1))
        return {"status": "connected"}
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        raise HTTPException(status_code=503, detail="Database unreachable")

# --- Conversations & Chat Test ---
@api_router.get("/conversations", response_model=List[ConversationResponse])
async def list_conversations(
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    # Strategy: List customers ordered by last_interaction, and fetch their last message.
    # To be efficient, we might just query customers with conversations.
    # For now, let's query customers who have interactions.
    
    stmt = (
        select(Customer)
        .order_by(desc(Customer.last_interaction))
        .limit(50)
    )
    result = await db.execute(stmt)
    customers = result.scalars().all()
    
    response = []
    for customer in customers:
        # Get last message content
        last_msg = await db.scalar(
            select(Conversation)
            .where(Conversation.customer_id == customer.id)
            .order_by(desc(Conversation.created_at))
            .limit(1)
        )
        
        preview = "No messages"
        if last_msg:
            preview = last_msg.content[:50] + "..." if len(last_msg.content) > 50 else last_msg.content
            
        response.append(ConversationResponse(
            id=customer.id, # Using customer_id as conversation ID for now since it's 1:1 in this view
            customer_name=customer.name,
            phone=customer.phone,
            last_message_at=customer.last_interaction,
            last_message_preview=preview
        ))
        
    return response

@api_router.post("/chat/test")
async def chat_test(
    request: ChatTestRequest,
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    # Mock context for admin testing
    logger.info(f"Admin {current_user.username} testing agent with message: {request.message}")
    
    # We use the agent directly. 
    # NOTE: The agent usually replies via WhatsApp API. 
    # We need to intercept the reply or use a method that returns the reply.
    # The current customer_agent.process_message sends to Evolution API.
    
    # To make this work for UI, we might need a method in agent that returns the text 
    # OR we mock the output.
    
    # Check customer_service_agent.py to see if we can get the text return.
    # If process_message returns the generated response, we are good.
    # If it sends async, we might not get it back here easily without refactoring.
    
    # Temporary: Use LLM service directly to simulate agent response for testing logic.
    # Or better: Create a "test_mode" in process_message?
    
    # For now, let's assume we want to test the LLM logic:
    try:
        # Construct context similar to what agent does
        # Construct context similar to what agent does
        messages = [
            {"role": "system", "content": "You are a helpful assistant for testing purposes."},
            {"role": "user", "content": request.message}
        ]
        
        # We invoke LLM service directly to get the response string
        response = await llm_service.get_chat_response(messages)
        return {"reply": response.content}
        
    except Exception as e:
        logger.error(f"Error in chat test: {e}")
        return {"reply": "Erro ao processar mensagem de teste."}

# --- Analytics ---
@api_router.get("/analytics/dashboard")
async def get_analytics_dashboard(
    current_user: Annotated[AdminUser, Depends(get_current_user)],
):
    overview = await analytics_service.get_overview_stats()
    performance = await analytics_service.get_performance_metrics()
    business = await analytics_service.get_business_impact()
    
    return {
        "overview": overview,
        "performance": performance,
        "business": business
    }
