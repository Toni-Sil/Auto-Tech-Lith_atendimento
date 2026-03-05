from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import Annotated
from src.api.auth import get_current_user, AdminUser, RequirePermissions
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, or_
from typing import List, Optional
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


# --- Config APIs ---
from src.schemas import SystemConfigUpdate
@api_router.get("/config")
async def get_system_config(
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(SystemConfig).where(SystemConfig.tenant_id == current_user.tenant_id))
    configs = result.scalars().all()
    # Return as dict for easy frontend consumption
    return {c.key: c.value for c in configs if not c.is_secret}

@api_router.post("/config")
async def update_system_config(
    data: SystemConfigUpdate,
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    for item in data.configs:
        stmt = select(SystemConfig).where(SystemConfig.key == item.key, SystemConfig.tenant_id == current_user.tenant_id)
        config = await db.scalar(stmt)
        if config:
            config.value = item.value
        else:
            config = SystemConfig(key=item.key, value=item.value, tenant_id=current_user.tenant_id)
            db.add(config)
    await db.commit()
    return {"status": "success"}

from fastapi import UploadFile, File
import shutil
import uuid

@api_router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    current_user: Annotated[AdminUser, Depends(get_current_user)] = None, # Workaround if it's meant to be optional, or just remove '= Depends()'
):
    """
    Endpoint for uploading images and PDFs (for Avatar and Logo).
    Returns the static URL to access the uploaded file.
    """
    # Create the directory if it doesn't exist
    upload_dir = os.path.join(os.getcwd(), "frontend", "assets", "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    
    # Generate a unique filename to prevent collisions and caching issues
    file_ext = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(upload_dir, unique_filename)
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        logger.error(f"Error saving uploaded file: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to save file")
    
    # Return the URL that the frontend can use to access this file
    # The frontend is mounted statically at /static/ from the frontend/ folder
    static_url = f"/static/assets/uploads/{unique_filename}"
    
    return {"status": "success", "url": static_url, "filename": file.filename}

# --- Dashboard Stats ---
@api_router.get("/stats", response_model=DashboardStats)
@api_router.get("/stats", response_model=DashboardStats)
async def get_stats(
    current_user: Annotated[AdminUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    # Estatísticas básicas
    active_customers = await db.scalar(select(func.count(Customer.id)).where(Customer.tenant_id == current_user.tenant_id))
    # Tickets abertos
    open_tickets = await db.scalar(select(func.count(Ticket.id)).where(Ticket.status == TicketStatus.OPEN, Ticket.tenant_id == current_user.tenant_id))
    # Reuniões agendadas
    scheduled_meetings = await db.scalar(select(func.count(Meeting.id)).where(
        Meeting.status == MeetingStatus.SCHEDULED,
        Meeting.date >= date.today(),
        Meeting.tenant_id == current_user.tenant_id
    ))
    # Conversas de hoje
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_conversations = await db.scalar(select(func.count(Conversation.id)).where(
        Conversation.created_at >= today_start,
        Conversation.tenant_id == current_user.tenant_id
    ))

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
        .where(
            Customer.tenant_id == current_user.tenant_id,
            Customer.source != "internal_test"
        )
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
    existing = await db.scalar(select(Customer).where(Customer.phone == customer.phone, Customer.tenant_id == current_user.tenant_id))
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

    new_customer = Customer(**customer.model_dump(), tenant_id=current_user.tenant_id)
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
    existing = await db.scalar(select(Customer).where(Customer.id == customer_id, Customer.tenant_id == current_user.tenant_id))
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
    current_user: Annotated[AdminUser, Depends(RequirePermissions(["customers:delete"]))],
    db: AsyncSession = Depends(get_db)
):
    customer = await db.scalar(select(Customer).where(Customer.id == customer_id, Customer.tenant_id == current_user.tenant_id))
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
    result = await db.execute(
        select(Ticket, Customer.name)
        .join(Customer)
        .where(Ticket.tenant_id == current_user.tenant_id)
        .order_by(desc(Ticket.created_at))
    )
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
    result = await db.execute(
        select(Meeting, Customer.name)
        .join(Customer)
        .where(Meeting.tenant_id == current_user.tenant_id)
        .order_by(Meeting.date, Meeting.time)
    )
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
    # 1. Enforce ownership and check if customer belongs to tenant
    customer = await db.scalar(select(Customer).where(Customer.id == meeting.customer_id, Customer.tenant_id == current_user.tenant_id))
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found in your tenant")
        
    new_meeting = Meeting(**meeting.model_dump(), tenant_id=current_user.tenant_id)
    db.add(new_meeting)
    
    # 2. Automate Customer Status Update
    if new_meeting.type == MeetingType.BRIEFING:
        customer.status = "briefing"
    elif new_meeting.type == MeetingType.PROPOSAL:
        customer.status = "proposal"
            
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
    existing = await db.scalar(select(Meeting).where(Meeting.id == meeting_id, Meeting.tenant_id == current_user.tenant_id))
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
    current_user: Annotated[AdminUser, Depends(RequirePermissions(["meetings:delete"]))],
    db: AsyncSession = Depends(get_db)
):
    meeting = await db.scalar(select(Meeting).where(Meeting.id == meeting_id, Meeting.tenant_id == current_user.tenant_id))
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    
    await db.delete(meeting)
    await db.commit()
    return {"status": "deleted"}

# --- Webhooks ---
from fastapi import Request
@api_router.post("/webhooks/whatsapp")
async def whatsapp_webhook(request: Request, background_tasks: BackgroundTasks, instance_name: Optional[str] = None):
    logger.info(f"--- WHATSAPP WEBHOOK HIT --- Instance: {instance_name}")
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
    
    # Identify instance from payload if not in URL
    if not instance_name:
        instance_name = payload.get("instance")
        
    event_type = payload.get("event")
    
    # Handle connection updates to keep UI synchronized
    if event_type == "connection.update":
        state = payload.get("data", {}).get("state")
        if state and instance_name:
            from src.models.database import async_session
            from src.models.whatsapp import EvolutionInstance
            from sqlalchemy import update
            async with async_session() as session:
                new_status = "connected" if state == 'open' else ("disconnected" if state == 'close' else "pending")
                stmt = update(EvolutionInstance).where(EvolutionInstance.instance_name == instance_name).values(status=new_status)
                await session.execute(stmt)
                await session.commit()
                logger.info(f"Updated connection status for {instance_name} to {new_status}")
            return {"status": "success", "reason": "connection status updated to " + new_status}
    
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
        # Log — o agente via process_message também chamará mark_message_as_read
        logger.info(f"Incoming message from {remote_jid} id={message_id}")

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
            context={
                "phone": phone,
                "name": push_name,
                "remote_jid": remote_jid,    # para marcar como lido
                "message_id": message_id,    # para marcar como lido
                "instance_name": instance_name
            }
        )
        return {"status": "processing"}
    
    return {"status": "ignored", "reason": "invalid data"}

# --- Health & Status APIs ---
@api_router.get("/ping")
async def ping():
    """Endpoint for external APIs to confirm system is reachable."""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

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
        .where(
            Customer.tenant_id == current_user.tenant_id,
            Customer.source != "internal_test"
        )
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
    from src.models.conversation import Conversation, MessageRole
    logger.info(f"Admin {current_user.username} testing agent with message: {request.message}")
    
    try:
        test_phone = f"test_{current_user.id}"
        stmt = select(Customer).where(
            Customer.tenant_id == current_user.tenant_id, 
            Customer.phone == test_phone
        )
        mock_customer = await db.scalar(stmt)
        if not mock_customer:
            mock_customer = Customer(
                name=current_user.name or current_user.username or "Admin Test",
                phone=test_phone,
                email=current_user.email or "admin@atendente.ai",
                tenant_id=current_user.tenant_id,
                company="Atendente.ai" if not current_user.tenant_id else "Sua Empresa",
                source="internal_test"
            )
            db.add(mock_customer)
            await db.commit()
            await db.refresh(mock_customer)

        stmt = select(Conversation).where(Conversation.customer_id == mock_customer.id).order_by(Conversation.created_at)
        history = (await db.execute(stmt)).scalars().all()
        
        if current_user.tenant_id is None:
            # Master Admin: usa AdminAgent
            from src.agents.admin_agent import AdminAgent
            admin_agent = AdminAgent()
            
            # Autenticação fake / injetando o contexto 
            context = {"user_id": current_user.id, "username": current_user.name}
            final_response = await admin_agent.process_message(request.message, context)
            
        else:
            # Tenant Test
            system_prompt = await customer_agent.load_system_prompt(mock_customer, "test")
            messages = [{"role": "system", "content": system_prompt}]
            for msg in history:
                messages.append({"role": msg.role, "content": msg.content})
            messages.append({"role": "user", "content": request.message})
            
            response = await llm_service.get_chat_response(messages)
            final_response = response.content

        # Persist to DB
        user_msg = Conversation(
            tenant_id=current_user.tenant_id,
            customer_id=mock_customer.id,
            role=MessageRole.USER,
            content=request.message,
        )
        db.add(user_msg)
        
        ast_msg = Conversation(
            tenant_id=current_user.tenant_id,
            customer_id=mock_customer.id,
            role=MessageRole.ASSISTANT,
            content=final_response,
        )
        db.add(ast_msg)
        await db.commit()
        
        return {"reply": final_response}
        
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


# ─────────────────────────────────────────────
# Agent Profiles
# ─────────────────────────────────────────────
from src.services.profile_service import profile_service
from src.schemas import AgentProfileCreate, AgentProfileResponse
from src.services.prompt_generator_service import prompt_generator_service

@api_router.get("/profiles", response_model=List[AgentProfileResponse])
async def list_profiles(current_user: Annotated[AdminUser, Depends(get_current_user)]):
    profiles = await profile_service.list_profiles(tenant_id=current_user.tenant_id)
    return [AgentProfileResponse.model_validate(p) for p in profiles]

@api_router.post("/profiles", response_model=AgentProfileResponse)
async def create_profile(
    data: AgentProfileCreate,
    current_user: Annotated[AdminUser, Depends(get_current_user)],
):
    profile_data = data.model_dump()
    
    # Auto-fill logic
    base_prompt = profile_data.get("base_prompt")
    if base_prompt:
        # Prevent overriding if objective is already set explicitly by the user
        # (Assuming an empty objective means we should try to auto-fill)
        if not profile_data.get("objective"):
            extracted = await prompt_generator_service.analyze_prompt(base_prompt)
            for field, value in extracted.items():
                if field in profile_data:
                    current_val = profile_data.get(field)
                    is_empty_or_default = (
                        not current_val 
                        or current_val in ["geral", "neutro", "equilibrado", "equilibrada"]
                    )
                    if is_empty_or_default and value:
                        profile_data[field] = value

    profile = await profile_service.create_profile(profile_data, tenant_id=current_user.tenant_id)
    return AgentProfileResponse.model_validate(profile)

@api_router.put("/profiles/{profile_id}", response_model=AgentProfileResponse)
async def update_profile(
    profile_id: int,
    data: AgentProfileCreate,
    current_user: Annotated[AdminUser, Depends(get_current_user)],
):
    profile_data = data.model_dump(exclude_unset=True)
    
    # Auto-fill logic
    base_prompt = profile_data.get("base_prompt")
    if base_prompt:
        if not profile_data.get("objective"):
            extracted = await prompt_generator_service.analyze_prompt(base_prompt)
            for field, value in extracted.items():
                if field in profile_data:
                    current_val = profile_data.get(field)
                    is_empty_or_default = (
                        not current_val 
                        or current_val in ["geral", "neutro", "equilibrado", "equilibrada"]
                    )
                    if is_empty_or_default and value:
                        profile_data[field] = value

    profile = await profile_service.update_profile(profile_id, profile_data, tenant_id=current_user.tenant_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return AgentProfileResponse.model_validate(profile)

@api_router.post("/profiles/{profile_id}/activate", response_model=AgentProfileResponse)
async def activate_profile(
    profile_id: int,
    current_user: Annotated[AdminUser, Depends(get_current_user)],
):
    profile = await profile_service.activate_profile(profile_id, tenant_id=current_user.tenant_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return AgentProfileResponse.model_validate(profile)

@api_router.delete("/profiles/{profile_id}")
async def delete_profile(
    profile_id: int,
    current_user: Annotated[AdminUser, Depends(RequirePermissions(["profiles:delete"]))],
):
    success = await profile_service.delete_profile(profile_id, tenant_id=current_user.tenant_id)
    if not success:
        raise HTTPException(status_code=400, detail="Profile not found or is currently active")
    return {"status": "deleted"}


# ─────────────────────────────────────────────
# Webhook Configs
# ─────────────────────────────────────────────
from src.services.webhook_config_service import webhook_config_service
from src.schemas import WebhookConfigCreate, WebhookConfigResponse

@api_router.get("/webhooks", response_model=List[WebhookConfigResponse])
async def list_webhooks(current_user: Annotated[AdminUser, Depends(get_current_user)]):
    webhooks = await webhook_config_service.list_webhooks(tenant_id=current_user.tenant_id)
    return [WebhookConfigResponse.model_validate(w) for w in webhooks]

@api_router.post("/webhooks", response_model=WebhookConfigResponse)
async def create_webhook(
    data: WebhookConfigCreate,
    current_user: Annotated[AdminUser, Depends(get_current_user)],
):
    webhook = await webhook_config_service.create_webhook(data.model_dump(), tenant_id=current_user.tenant_id)
    return WebhookConfigResponse.model_validate(webhook)

@api_router.put("/webhooks/{webhook_id}", response_model=WebhookConfigResponse)
async def update_webhook(
    webhook_id: int,
    data: WebhookConfigCreate,
    current_user: Annotated[AdminUser, Depends(get_current_user)],
):
    webhook = await webhook_config_service.update_webhook(webhook_id, data.model_dump(exclude_unset=True), tenant_id=current_user.tenant_id)
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return WebhookConfigResponse.model_validate(webhook)

@api_router.delete("/webhooks/{webhook_id}")
async def delete_webhook(
    webhook_id: int,
    current_user: Annotated[AdminUser, Depends(get_current_user)],
):
    success = await webhook_config_service.delete_webhook(webhook_id, tenant_id=current_user.tenant_id)
    if not success:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {"status": "deleted"}

@api_router.post("/webhooks/{webhook_id}/test")
async def test_webhook(
    webhook_id: int,
    current_user: Annotated[AdminUser, Depends(get_current_user)],
):
    result = await webhook_config_service.test_webhook(webhook_id, tenant_id=current_user.tenant_id)
    return result


# ─────────────────────────────────────────────
# Prompt Generator
# ─────────────────────────────────────────────
from src.services.prompt_generator_service import prompt_generator_service
from src.schemas import PromptGenerateRequest, PromptGenerateResponse

@api_router.get("/prompts/templates")
async def get_prompt_templates(current_user: Annotated[AdminUser, Depends(get_current_user)]):
    return {"templates": prompt_generator_service.get_templates()}

@api_router.post("/prompts/generate", response_model=PromptGenerateResponse)
async def generate_prompt(
    request: PromptGenerateRequest,
    current_user: Annotated[AdminUser, Depends(get_current_user)],
):
    answers = request.model_dump()
    prompt = prompt_generator_service.generate_prompt(answers)
    return PromptGenerateResponse(
        prompt=prompt,
        niche=request.niche,
        tone=request.tone,
    )

import subprocess
import sys
@api_router.get("/validate-hack")
async def validate_hack():
    try:
        res = subprocess.run([sys.executable, "/media/toni-sil/Arquivos3/agentes/antigravity-awesome-skills/scripts/validate_skills.py"], capture_output=True, text=True)
        return {"status": "ok", "out": res.stdout, "err": res.stderr}
    except Exception as e:
        return {"error": str(e)}
