import csv
import io
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.models.customer import Customer
from src.models.ticket import Ticket
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

class ReportService:
    async def generate_customers_csv(self, session: AsyncSession, tenant_id: int) -> str:
        """Generates a CSV string containing all customers for a tenant."""
        result = await session.execute(select(Customer).where(Customer.tenant_id == tenant_id))
        customers = result.scalars().all()
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow(["ID", "Name", "Email", "Phone", "Document", "Created At"])
        
        for c in customers:
            writer.writerow([
                c.id, 
                c.name, 
                c.email or "", 
                c.phone or "", 
                c.document or "", 
                c.created_at.isoformat() if c.created_at else ""
            ])
            
        return output.getvalue()

    async def generate_tickets_csv(self, session: AsyncSession, tenant_id: int) -> str:
        """Generates a CSV string containing all tickets for a tenant."""
        result = await session.execute(select(Ticket).where(Ticket.tenant_id == tenant_id))
        tickets = result.scalars().all()
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow(["ID", "Customer ID", "Title", "Status", "Priority", "Created At"])
        
        for t in tickets:
            writer.writerow([
                t.id, 
                t.customer_id, 
                t.title, 
                t.status, 
                t.priority, 
                t.created_at.isoformat() if t.created_at else ""
            ])
            
        return output.getvalue()

report_service = ReportService()
