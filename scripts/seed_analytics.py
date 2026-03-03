
import asyncio
import random
from datetime import datetime, timedelta
from src.models.database import engine
from src.models.customer import Customer
from src.models.ticket import Ticket, TicketStatus, TicketPriority
from src.models.conversation import Conversation, MessageRole
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

async def main():
    print("Seeding Analytics Data...")
    
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as db:
        # Create some customers with different sources
        sources = ['whatsapp', 'web', 'instagram']
        statuses = ['em_processo', 'briefing', 'proposal', 'monthly', 'completed']
        
        for i in range(20):
            phone = f"551199999{i:04d}"
            existing = await db.scalar(select(Customer).where(Customer.phone == phone))
            
            if not existing:
                customer = Customer(
                    name=f"Customer {i}",
                    phone=phone,
                    email=f"customer{i}@example.com",
                    company=f"Company {i}",
                    status=random.choice(statuses),
                    source=random.choice(sources),
                    churned=random.choice([True, False, False, False]), # 25% churn chance
                    created_at=datetime.now() - timedelta(days=random.randint(0, 30))
                )
                db.add(customer)
                await db.flush() # get ID
                
                # Create Tickets
                for _ in range(random.randint(0, 3)):
                    is_automated = random.choice([True, False])
                    rating = random.randint(3, 5) if is_automated else random.randint(1, 5)
                    
                    ticket = Ticket(
                        customer_id=customer.id,
                        subject=f"Issue {random.randint(1000, 9999)}",
                        status=random.choice(list(TicketStatus)),
                        priority=random.choice(list(TicketPriority)),
                        category=random.choice(['support', 'sales', 'inquiry']),
                        is_automated=is_automated,
                        rating=rating if random.choice([True, False]) else None,
                        created_at=datetime.now() - timedelta(days=random.randint(0, 10))
                    )
                    db.add(ticket)
                
                # Create Conversations
                for _ in range(random.randint(5, 20)):
                     msg = Conversation(
                         customer_id=customer.id,
                         role=random.choice(list(MessageRole)),
                         content="Simulated message content...",
                         created_at=datetime.now() - timedelta(minutes=random.randint(0, 10000))
                     )
                     db.add(msg)
            
        await db.commit()
        print("Analytics Data Seeded.")

if __name__ == "__main__":
    asyncio.run(main())
