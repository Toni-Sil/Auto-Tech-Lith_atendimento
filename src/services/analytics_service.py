
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.database import async_session
from src.models.customer import Customer
from src.models.ticket import Ticket, TicketStatus
from src.models.conversation import Conversation
from datetime import datetime, timedelta

class AnalyticsService:
    async def get_overview_stats(self):
        async with async_session() as db:
            # 1. Volume de conversas por canal (Customer.source)
            channel_stmt = (
                select(Customer.source, func.count(Customer.id))
                .group_by(Customer.source)
            )
            channels = (await db.execute(channel_stmt)).all()
            
            # 2. Status das Conversas (Tickets?) ou Clientes?
            # Vamos usar TicketStatus por enquanto
            today = datetime.now().date()
            ticket_stmt = (
                select(Ticket.status, func.count(Ticket.id))
                .where(func.date(Ticket.created_at) == today)
                .group_by(Ticket.status)
            )
            ticket_stats = (await db.execute(ticket_stmt)).all()
            
            return {
                "channels": {source: count for source, count in channels},
                "tickets_today": {status: count for status, count in ticket_stats}
            }

    async def get_performance_metrics(self):
        async with async_session() as db:
            # 1. Taxa de Automação (Tickets resolved by bot / Total resolved)
            # Ticket.is_automated field
            automation_stmt = (
                select(
                    func.count(Ticket.id).filter(Ticket.is_automated == True).label("automated"),
                    func.count(Ticket.id).label("total")
                )
                .where(Ticket.status == TicketStatus.RESOLVED)
            )
            auto_stats = (await db.execute(automation_stmt)).one()
            automation_rate = (auto_stats.automated / auto_stats.total * 100) if auto_stats.total > 0 else 0
            
            # 2. Satisfação (Rating)
            csat_stmt = select(func.avg(Ticket.rating)).where(Ticket.rating.isnot(None))
            avg_rating = await db.scalar(csat_stmt) or 0
            
            return {
                "automation_rate": round(automation_rate, 2),
                "csat": round(avg_rating, 2)
            }
            
    async def get_business_impact(self):
        async with async_session() as db:
            # 1. Funil de Vendas (Baseado em Customer.status)
            # Statuses: em_processo -> briefing -> proposal -> monthly -> completed
            funnel_stmt = (
                select(Customer.status, func.count(Customer.id))
                .group_by(Customer.status)
            )
            funnel_data = (await db.execute(funnel_stmt)).all()
            
            # 2. Leads (Total de novos clientes nos ultimos 30 dias)
            thirty_days_ago = datetime.now() - timedelta(days=30)
            leads_stmt = select(func.count(Customer.id)).where(Customer.created_at >= thirty_days_ago)
            new_leads = await db.scalar(leads_stmt)
            
            return {
                "funnel": {status: count for status, count in funnel_data},
                "new_leads_30d": new_leads
            }

analytics_service = AnalyticsService()
