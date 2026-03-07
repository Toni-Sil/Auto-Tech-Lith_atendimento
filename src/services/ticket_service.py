"""
Ticket Service - Support Ticket Management

Handles creation, tracking, and management of customer support tickets.
Integrates with Butler agent for automatic triage and escalation.
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from enum import Enum
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.database import async_session
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class TicketPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"
    CRITICAL = "critical"


class TicketStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    WAITING_CUSTOMER = "waiting_customer"
    WAITING_INTERNAL = "waiting_internal"
    RESOLVED = "resolved"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class TicketCategory(str, Enum):
    TECHNICAL = "technical"
    BILLING = "billing"
    FEATURE_REQUEST = "feature_request"
    BUG = "bug"
    INTEGRATION = "integration"
    TRAINING = "training"
    OTHER = "other"


class TicketService:
    """
    Manages support tickets with SLA tracking and auto-escalation.
    """
    
    # SLA targets in hours
    SLA_TARGETS = {
        TicketPriority.CRITICAL: 1,
        TicketPriority.URGENT: 4,
        TicketPriority.HIGH: 24,
        TicketPriority.MEDIUM: 48,
        TicketPriority.LOW: 72
    }
    
    async def create_ticket(
        self,
        customer_id: int,
        subject: str,
        description: str,
        category: Optional[TicketCategory] = None,
        priority: Optional[TicketPriority] = None,
        tenant_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Create a new support ticket.
        
        If priority is not specified, it will be auto-assigned based on
        keyword analysis.
        """
        async with async_session() as session:
            try:
                from src.models.ticket import Ticket
                
                # Auto-detect priority if not provided
                if priority is None:
                    priority = self._detect_priority(subject, description)
                
                # Auto-detect category if not provided
                if category is None:
                    category = self._detect_category(subject, description)
                
                # Calculate SLA deadline
                sla_hours = self.SLA_TARGETS.get(priority, 48)
                sla_deadline = datetime.now() + timedelta(hours=sla_hours)
                
                ticket = Ticket(
                    customer_id=customer_id,
                    tenant_id=tenant_id,
                    subject=subject[:200],
                    description=description,
                    category=category,
                    priority=priority,
                    status=TicketStatus.OPEN,
                    sla_deadline=sla_deadline,
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                )
                
                session.add(ticket)
                await session.commit()
                await session.refresh(ticket)
                
                logger.info(
                    f"Ticket #{ticket.id} created: {priority.value} / {category.value} "
                    f"(SLA: {sla_deadline.strftime('%Y-%m-%d %H:%M')})"
                )
                
                # Notify Butler for triage if high priority
                if priority in [TicketPriority.CRITICAL, TicketPriority.URGENT]:
                    await self._notify_butler(ticket)
                
                return self._ticket_to_dict(ticket)
                
            except ImportError:
                logger.error("Ticket model not found in database")
                return {"error": "Ticket system not configured"}
            except Exception as e:
                logger.error(f"Create ticket error: {e}", exc_info=True)
                return {"error": str(e)}
    
    async def get_ticket(
        self,
        ticket_id: int,
        tenant_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get ticket details by ID.
        """
        async with async_session() as session:
            try:
                from src.models.ticket import Ticket
                
                stmt = select(Ticket).where(Ticket.id == ticket_id)
                
                if tenant_id is not None:
                    stmt = stmt.where(Ticket.tenant_id == tenant_id)
                
                result = await session.execute(stmt)
                ticket = result.scalar_one_or_none()
                
                if not ticket:
                    return None
                
                return self._ticket_to_dict(ticket)
                
            except ImportError:
                return None
            except Exception as e:
                logger.error(f"Get ticket error: {e}")
                return None
    
    async def update_ticket_status(
        self,
        ticket_id: int,
        status: TicketStatus,
        comment: Optional[str] = None,
        tenant_id: Optional[int] = None
    ) -> bool:
        """
        Update ticket status with optional comment.
        """
        async with async_session() as session:
            try:
                from src.models.ticket import Ticket, TicketComment
                
                stmt = select(Ticket).where(Ticket.id == ticket_id)
                if tenant_id is not None:
                    stmt = stmt.where(Ticket.tenant_id == tenant_id)
                
                result = await session.execute(stmt)
                ticket = result.scalar_one_or_none()
                
                if not ticket:
                    return False
                
                old_status = ticket.status
                ticket.status = status
                ticket.updated_at = datetime.now()
                
                if status in [TicketStatus.RESOLVED, TicketStatus.CLOSED]:
                    ticket.resolved_at = datetime.now()
                
                # Add status change comment
                if comment:
                    ticket_comment = TicketComment(
                        ticket_id=ticket_id,
                        author="system",
                        content=f"Status changed: {old_status.value} → {status.value}\n\n{comment}",
                        created_at=datetime.now()
                    )
                    session.add(ticket_comment)
                
                await session.commit()
                
                logger.info(f"Ticket #{ticket_id} status: {old_status.value} → {status.value}")
                return True
                
            except ImportError:
                return False
            except Exception as e:
                logger.error(f"Update ticket error: {e}")
                return False
    
    async def list_customer_tickets(
        self,
        customer_id: int,
        status: Optional[TicketStatus] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        List tickets for a specific customer.
        """
        async with async_session() as session:
            try:
                from src.models.ticket import Ticket
                
                stmt = select(Ticket).where(
                    Ticket.customer_id == customer_id
                ).order_by(Ticket.created_at.desc()).limit(limit)
                
                if status:
                    stmt = stmt.where(Ticket.status == status)
                
                result = await session.execute(stmt)
                tickets = result.scalars().all()
                
                return [self._ticket_to_dict(t) for t in tickets]
                
            except ImportError:
                return []
            except Exception as e:
                logger.error(f"List tickets error: {e}")
                return []
    
    def _detect_priority(self, subject: str, description: str) -> TicketPriority:
        """
        Auto-detect priority based on keywords.
        """
        text = (subject + " " + description).lower()
        
        critical_keywords = ["down", "offline", "crash", "emergency", "urgente", "crítico", "parado"]
        urgent_keywords = ["urgent", "asap", "immediately", "não funciona", "erro crítico"]
        high_keywords = ["error", "bug", "issue", "problem", "erro", "problema"]
        
        if any(kw in text for kw in critical_keywords):
            return TicketPriority.CRITICAL
        if any(kw in text for kw in urgent_keywords):
            return TicketPriority.URGENT
        if any(kw in text for kw in high_keywords):
            return TicketPriority.HIGH
        
        return TicketPriority.MEDIUM
    
    def _detect_category(self, subject: str, description: str) -> TicketCategory:
        """
        Auto-detect category based on keywords.
        """
        text = (subject + " " + description).lower()
        
        if any(kw in text for kw in ["bug", "erro", "error", "crash", "quebrado"]):
            return TicketCategory.BUG
        if any(kw in text for kw in ["pagamento", "cobrança", "billing", "invoice", "fatura"]):
            return TicketCategory.BILLING
        if any(kw in text for kw in ["integração", "api", "webhook", "connect"]):
            return TicketCategory.INTEGRATION
        if any(kw in text for kw in ["feature", "funcionalidade", "recurso", "sugestão"]):
            return TicketCategory.FEATURE_REQUEST
        if any(kw in text for kw in ["treinamento", "como", "tutorial", "ajuda"]):
            return TicketCategory.TRAINING
        
        return TicketCategory.TECHNICAL
    
    async def _notify_butler(self, ticket: Any) -> None:
        """
        Notify Butler agent for high-priority tickets.
        """
        try:
            from src.services.telegram_service import telegram_service
            
            message = (
                f"🚨 *Novo Ticket {ticket.priority.value.upper()}*\n\n"
                f"ID: #{ticket.id}\n"
                f"Categoria: {ticket.category.value}\n"
                f"Assunto: {ticket.subject}\n\n"
                f"SLA: {ticket.sla_deadline.strftime('%d/%m/%Y %H:%M')}"
            )
            
            await telegram_service.send_message(message)
        except Exception as e:
            logger.warning(f"Failed to notify Butler: {e}")
    
    def _ticket_to_dict(self, ticket: Any) -> Dict[str, Any]:
        """Convert ticket model to dict."""
        return {
            "id": ticket.id,
            "subject": ticket.subject,
            "description": ticket.description,
            "category": ticket.category.value if hasattr(ticket.category, 'value') else ticket.category,
            "priority": ticket.priority.value if hasattr(ticket.priority, 'value') else ticket.priority,
            "status": ticket.status.value if hasattr(ticket.status, 'value') else ticket.status,
            "customer_id": ticket.customer_id,
            "sla_deadline": ticket.sla_deadline.isoformat() if ticket.sla_deadline else None,
            "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
            "resolved_at": ticket.resolved_at.isoformat() if hasattr(ticket, 'resolved_at') and ticket.resolved_at else None
        }


# Singleton
ticket_service = TicketService()
