from datetime import datetime, date, time
from typing import Optional, List
from sqlalchemy import select
from src.models.database import async_session
from src.models.customer import Customer
from src.models.lead import Lead, LeadStatus
from src.models.meeting import Meeting, MeetingType, MeetingStatus
from src.utils.logger import setup_logger
from src.services.telegram_service import telegram_service

logger = setup_logger(__name__)

from src.models.audit import AuditLog

async def update_customer_info(customer_id: int, name: Optional[str] = None, email: Optional[str] = None, company: Optional[str] = None, demand: Optional[str] = None) -> str:
    """Atualiza as informações cadastrais do cliente e sincroniza com o CRM se for Master."""
    async with async_session() as session:
        result = await session.execute(select(Customer).where(Customer.id == customer_id))
        customer = result.scalar_one_or_none()
        
        if not customer:
            return "Erro: Cliente não encontrado."
            
        if name: customer.name = name
        if email: customer.email = email
        if company: customer.company = company
        if demand: customer.initial_demand = demand
        
        customer.updated_at = datetime.now()

        # 🔥 SYNC: Se o tenant_id for None, este é um prospecto do Master Admin
        # Devemos criar ou atualizar um Lead no CRM interno.
        if customer.tenant_id is None:
            try:
                # Procurar lead existente pelo telefone
                stmt = select(Lead).where(Lead.phone == customer.phone)
                lead = (await session.execute(stmt)).scalar_one_or_none()
                
                if not lead:
                    lead = Lead(
                        name=customer.name or "Novo Lead (WhatsApp)",
                        phone=customer.phone,
                        email=customer.email,
                        company=customer.company,
                        source="WhatsApp",
                        status=LeadStatus.CONTACT,
                        notes=f"Auto-registrado via Max (Atendimento).\nDemanda: {customer.initial_demand or ''}"
                    )
                    session.add(lead)
                    
                    # Log de Auditoria para Registro de Novo Lead
                    audit = AuditLog(
                        event_type="customer_registered_by_agent",
                        username=f"WA:{customer.phone}",
                        details=f"Novo Lead '{lead.name}' registrado pelo agente Max.",
                        ip_address="bot"
                    )
                    session.add(audit)
                    
                    logger.info(f"Sync: New Lead created for phone {customer.phone}")
                else:
                    # Update existing lead
                    if name: lead.name = name
                    if email: lead.email = email
                    if company: lead.company = company
                    if demand: 
                        lead.notes = (lead.notes or "") + f"\n\n[Atualização {datetime.now().strftime('%d/%m/%Y')}]: {demand}"
                    logger.info(f"Sync: Lead {lead.id} updated from Customer data")
            except Exception as e:
                logger.error(f"Sync Error (Customer -> Lead): {e}")
        
        await session.commit()
        
        logger.info(f"Customer {customer_id} updated: {name}, {email}, {company}")
        return "Dados do cliente atualizados com sucesso."

async def schedule_meeting(customer_id: int, meeting_type: str, date_str: str, time_str: str, notes: str = "") -> str:
    """Agenda uma reunião. Formato data: YYYY-MM-DD, Hora: HH:MM."""
    try:
        meeting_date = date.fromisoformat(date_str)
        meeting_time = time.fromisoformat(time_str)
        
        # Fuzzy match para tipo de reunião
        mt_input = meeting_type.lower().strip()
        if mt_input in [t.value for t in MeetingType]:
            m_type = MeetingType(mt_input)
        elif "brief" in mt_input:
            m_type = MeetingType.BRIEFING
        elif "prop" in mt_input:
            m_type = MeetingType.PROPOSAL
        elif "follow" in mt_input or "acompanha" in mt_input:
            m_type = MeetingType.FOLLOW_UP
        else:
             return f"Erro: Tipo de reunião '{meeting_type}' inválido. Use: {[t.value for t in MeetingType]}"

        async with async_session() as session:
            # Pegar dados do cliente primeiro para saber o tenant_id
            customer = await session.scalar(select(Customer).where(Customer.id == customer_id))
            if not customer:
                 return "Erro: Cliente não encontrado."

            # Verificar disponibilidade
            existing = await session.execute(select(Meeting).where(
                Meeting.date == meeting_date,
                Meeting.time == meeting_time,
                Meeting.status != MeetingStatus.CANCELLED
            ))
            if existing.scalar_one_or_none():
                return "Erro: Horário indisponível."

            new_meeting = Meeting(
                customer_id=customer_id,
                tenant_id=customer.tenant_id, # FIX: Usar o mesmo tenant do cliente
                type=m_type,
                date=meeting_date,
                time=meeting_time,
                notes=notes,
                status=MeetingStatus.SCHEDULED
            )
            session.add(new_meeting)
            
            # 🔥 SYNC: Se for Master, atualizar o status do Lead no CRM
            if customer.tenant_id is None:
                try:
                    stmt = select(Lead).where(Lead.phone == customer.phone)
                    lead = (await session.execute(stmt)).scalar_one_or_none()
                    if lead:
                        if m_type == MeetingType.BRIEFING:
                            lead.status = LeadStatus.BRIEFING
                        elif m_type == MeetingType.PROPOSAL:
                            lead.status = LeadStatus.PROPOSAL
                        logger.info(f"Sync: Lead {lead.id} status updated to {lead.status}")
                except Exception as e:
                     logger.error(f"Sync Error (Meeting -> Lead): {e}")

            await session.commit()
            
            # Notificar equipe no Telegram
            msg = (
                f"📅 *Nova Reunião Agendada ({m_type.value.capitalize()})*\n"
                f"👤 Cliente: {customer.name}\n"
                f"📞 Telefone: {customer.phone}\n"
                f"🏢 Empresa: {customer.company or 'N/A'}\n"
                f"📆 Data: {meeting_date.strftime('%d/%m/%Y')} às {meeting_time.strftime('%H:%M')}\n\n"
                f"📝 *Relatório de Serviço / Demanda:*\n"
                f"{notes or customer.initial_demand or 'Sem detalhes informados.'}"
            )
            if customer.tenant_id is None:
                msg = "🏢 *[MASTER ADMIN]*\n" + msg
            
            await telegram_service.send_message(msg)
            
            return f"Reunião de {m_type.value} agendada com sucesso para {date_str} às {time_str}."

    except ValueError as e:
        return f"Erro de formato de data/hora: {e}"
    except Exception as e:
        logger.error(f"Error scheduling meeting: {e}")
        return "Erro interno ao agendar reunião."

async def check_availability(tenant_id: Optional[int], date_str: Optional[str] = None) -> str:
    """
    Verifica a disponibilidade da agenda para um tenant específico.
    Se date_str for fornecido (YYYY-MM-DD), verifica aquele dia.
    Se não, verifica os próximos 3 dias úteis.
    """
    from datetime import timedelta
    
    today = date.today()
    check_days = []
    
    if date_str:
        try:
            target_date = date.fromisoformat(date_str)
            check_days.append(target_date)
        except ValueError:
            return "Erro: Formato de data inválido. Use YYYY-MM-DD."
    else:
        # Próximos 3 dias a partir de hoje
        for i in range(3):
            check_days.append(today + timedelta(days=i))

    report = []
    
    async with async_session() as session:
        for d in check_days:
            # Buscar reuniões agendadas para o dia e tenant (excluindo canceladas)
            stmt = select(Meeting).where(
                Meeting.tenant_id == tenant_id,
                Meeting.date == d,
                Meeting.status != MeetingStatus.CANCELLED
            ).order_by(Meeting.time)
            
            result = await session.execute(stmt)
            meetings = result.scalars().all()
            
            day_str = d.strftime("%d/%m/%Y")
            if not meetings:
                report.append(f"📅 {day_str}: Livre (09:00 - 18:00)")
            else:
                busy_slots = [m.time.strftime("%H:%M") for m in meetings]
                report.append(f"📅 {day_str}: Ocupado em {', '.join(busy_slots)}. Demais horários livres.")

    return "\n".join(report)


# ═══════════════════════════════════════════════════════════
# NEW TOOLS - Product Catalog & Support Tickets
# ═══════════════════════════════════════════════════════════

async def search_products(
    query: str,
    tenant_id: Optional[int] = None,
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None
) -> str:
    """
    Busca produtos/serviços no catálogo.
    
    Args:
        query: Termo de busca (nome, descrição)
        category: Filtro por categoria
        min_price/max_price: Faixa de preço
    """
    try:
        from src.services.catalog_service import catalog_service
        
        products = await catalog_service.search_products(
            query=query,
            tenant_id=tenant_id,
            category=category,
            min_price=min_price,
            max_price=max_price,
            limit=5
        )
        
        if not products:
            return "Nenhum produto encontrado com os critérios informados."
        
        result_lines = [f"Encontrei {len(products)} produto(s):\n"]
        for p in products:
            price_str = f"R$ {p['price']:.2f}"
            if not p.get('available', True):
                price_str += " (Indisponível)"
            
            result_lines.append(
                f"• **{p['name']}** - {price_str}\n"
                f"  {p.get('description', '')[:100]}..."
            )
        
        return "\n".join(result_lines)
        
    except Exception as e:
        logger.error(f"Error searching products: {e}")
        return "Erro ao buscar produtos. Tente novamente."


async def get_product_details(product_id: int, tenant_id: Optional[int] = None) -> str:
    """
    Obtém detalhes completos de um produto específico.
    """
    try:
        from src.services.catalog_service import catalog_service
        
        product = await catalog_service.get_product_by_id(product_id, tenant_id=tenant_id)
        
        if not product:
            return "Produto não encontrado."
        
        details = [
            f"**{product['name']}**",
            f"Preço: R$ {product['price']:.2f}",
            f"Categoria: {product.get('category', 'Geral')}",
            "",
            product.get('description', '')
        ]
        
        if product.get('stock') is not None:
            details.insert(3, f"Estoque: {product['stock']} unidades")
        
        return "\n".join(details)
        
    except Exception as e:
        logger.error(f"Error getting product details: {e}")
        return "Erro ao buscar detalhes do produto."


async def list_categories(tenant_id: Optional[int] = None) -> str:
    """
    Lista todas as categorias de produtos disponíveis.
    """
    try:
        from src.services.catalog_service import catalog_service
        
        categories = await catalog_service.get_categories(tenant_id=tenant_id)
        
        if not categories:
            return "Nenhuma categoria disponível no momento."
        
        return "Categorias disponíveis:\n• " + "\n• ".join(categories)
        
    except Exception as e:
        logger.error(f"Error listing categories: {e}")
        return "Erro ao listar categorias."


async def create_support_ticket(
    customer_id: int,
    subject: str,
    description: str,
    category: Optional[str] = None
) -> str:
    """
    Cria um chamado de suporte técnico para o cliente.
    
    Args:
        subject: Assunto do chamado
        description: Descrição detalhada do problema
        category: Categoria (technical, billing, integration, etc.)
    """
    try:
        from src.services.ticket_service import ticket_service, TicketCategory
        
        # Get customer info for tenant_id
        async with async_session() as session:
            customer = await session.scalar(select(Customer).where(Customer.id == customer_id))
            if not customer:
                return "Erro: Cliente não encontrado."
        
        # Map category string to enum
        category_enum = None
        if category:
            try:
                category_enum = TicketCategory(category.lower())
            except ValueError:
                pass
        
        ticket = await ticket_service.create_ticket(
            customer_id=customer_id,
            subject=subject,
            description=description,
            category=category_enum,
            tenant_id=customer.tenant_id
        )
        
        if "error" in ticket:
            return f"Erro ao criar chamado: {ticket['error']}"
        
        return (
            f"Chamado #{ticket['id']} criado com sucesso!\n"
            f"Prioridade: {ticket['priority'].upper()}\n"
            f"SLA: Resposta até {ticket['sla_deadline'][:16]}\n\n"
            f"Nossa equipe entrará em contato em breve."
        )
        
    except Exception as e:
        logger.error(f"Error creating ticket: {e}", exc_info=True)
        return "Erro ao criar chamado. Tente novamente ou entre em contato direto."


# Definição das ferramentas para o OpenAI
AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "update_customer_info",
            "description": "Atualiza nome, email, empresa ou demanda do cliente.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nome completo do cliente"},
                    "email": {"type": "string", "description": "Email do cliente"},
                    "company": {"type": "string", "description": "Nome da empresa (Obrigatório)"},
                    "demand": {"type": "string", "description": "Relatório detalhado do serviço ou problema relatado (Obrigatório)"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": "Verifica disponibilidade da agenda para um dia específico ou próximos dias.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_str": {"type": "string", "description": "Data específica para verificar (YYYY-MM-DD). Opcional."}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_meeting",
            "description": "Agenda uma reunião (Briefing, Proposta, Follow-up).",
            "parameters": {
                "type": "object",
                "properties": {
                    "meeting_type": {
                        "type": "string", 
                        "enum": ["briefing", "proposal", "follow-up"],
                        "description": "Tipo da reunião"
                    },
                    "date_str": {"type": "string", "description": "Data no formato YYYY-MM-DD"},
                    "time_str": {"type": "string", "description": "Hora no formato HH:MM"},
                    "notes": {"type": "string", "description": "Observações adicionais"}
                },
                "required": ["meeting_type", "date_str", "time_str"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "Busca produtos ou serviços no catálogo. Use quando o cliente perguntar sobre produtos, preços ou serviços disponíveis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Termo de busca (nome do produto/serviço)"},
                    "category": {"type": "string", "description": "Filtro por categoria (opcional)"},
                    "min_price": {"type": "number", "description": "Preço mínimo (opcional)"},
                    "max_price": {"type": "number", "description": "Preço máximo (opcional)"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_product_details",
            "description": "Obtém detalhes completos de um produto específico.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer", "description": "ID do produto"}
                },
                "required": ["product_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_categories",
            "description": "Lista todas as categorias de produtos disponíveis.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_support_ticket",
            "description": "Cria um chamado de suporte técnico para problemas, bugs ou dúvidas que requerem atenção da equipe.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "Assunto/título do chamado"},
                    "description": {"type": "string", "description": "Descrição detalhada do problema ou solicitação"},
                    "category": {
                        "type": "string",
                        "enum": ["technical", "billing", "feature_request", "bug", "integration", "training", "other"],
                        "description": "Categoria do chamado (opcional, será detectada automaticamente se não informado)"
                    }
                },
                "required": ["subject", "description"]
            }
        }
    }
]
