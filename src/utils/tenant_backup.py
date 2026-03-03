import os
import json
import asyncio
from datetime import datetime
from sqlalchemy import select
from src.models.database import async_session
from src.models.tenant import Tenant
from src.models.admin import AdminUser
from src.models.customer import Customer
from src.models.ticket import Ticket
from src.models.meeting import Meeting
from src.models.conversation import Conversation
from src.models.config_model import SystemConfig
from src.models.webhook_config import WebhookConfig
from src.models.agent_profile import AgentProfile

async def backup_tenant(tenant_id: int, backup_dir: str = "backups"):
    """
    Export all data associated with a specific tenant into a JSON file format.
    """
    os.makedirs(backup_dir, exist_ok=True)
    
    async with async_session() as db:
        tenant = await db.get(Tenant, tenant_id)
        if not tenant:
            print(f"Tenant {tenant_id} not found.")
            return False
            
        data_dump = {
            "tenant": {
                "id": tenant.id,
                "name": tenant.name,
                "subdomain": tenant.subdomain,
                "custom_domain": tenant.custom_domain,
            },
            "exported_at": datetime.now().isoformat(),
            "tables": {}
        }
        
        # Define tables to backup
        tables = {
            "admin_users": AdminUser,
            "customers": Customer,
            "tickets": Ticket,
            "meetings": Meeting,
            "conversations": Conversation,
            "system_config": SystemConfig,
            "webhook_configs": WebhookConfig,
            "agent_profiles": AgentProfile
        }
        
        for table_name, model in tables.items():
            result = await db.execute(select(model).where(model.tenant_id == tenant_id))
            records = result.scalars().all()
            
            table_data = []
            for record in records:
                # Convert SQLAlchemy model to dict
                record_dict = {c.name: getattr(record, c.name) for c in record.__table__.columns}
                # Convert datetime and other non-serializable formats
                for key, val in record_dict.items():
                    if isinstance(val, datetime):
                        record_dict[key] = val.isoformat()
                table_data.append(record_dict)
                
            data_dump["tables"][table_name] = table_data
            print(f"Backed up {len(table_data)} records for {table_name}")
            
        filename = f"tenant_{tenant_id}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(backup_dir, filename)
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data_dump, f, ensure_ascii=False, indent=2)
            
        print(f"Backup saved to {filepath}")
        return filepath

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python tenant_backup.py <tenant_id>")
        sys.exit(1)
        
    tenant_id = int(sys.argv[1])
    asyncio.run(backup_tenant(tenant_id))
