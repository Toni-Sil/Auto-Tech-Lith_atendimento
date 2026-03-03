import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from src.config import settings

async def apply_migration():
    """ Apply the new Role tables and columns to the database """
    print("Starting RBAC Migration...")
    engine = create_async_engine(settings.DATABASE_URL, echo=True)
    
    async with engine.begin() as conn:
        try:
            print("Creating roles table...")
            await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER REFERENCES tenants(id),
                name VARCHAR NOT NULL,
                description TEXT,
                permissions JSON DEFAULT '[]',
                is_system BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """))
            print("Roles table created.")
            
            print("Adding role_id column to admin_users...")
            try:
                await conn.execute(text("ALTER TABLE admin_users ADD COLUMN role_id INTEGER REFERENCES roles(id)"))
            except Exception as e:
                print(f"Skipping column constraint addition: {e} (might already exist)")
            
            print("Inserting default Admin role for Default Tenant (id=1)...")
            await conn.execute(text("""
            INSERT INTO roles (tenant_id, name, description, permissions, is_system) 
            SELECT 1, 'Administrador do Sistema', 'Acesso total', '["*"]', 1
            WHERE NOT EXISTS (SELECT 1 FROM roles WHERE name='Administrador do Sistema' AND tenant_id=1)
            """))
            
            print("Updating existing admin_users with Default Admin Role...")
            await conn.execute(text("""
            UPDATE admin_users SET role_id = (SELECT id FROM roles WHERE name='Administrador do Sistema' AND tenant_id=1 LIMIT 1)
            WHERE role_id IS NULL AND tenant_id=1
            """))
            
            print("Migration applied successfully!")
            
        except Exception as e:
            print(f"Error during migration: {e}")

if __name__ == "__main__":
    asyncio.run(apply_migration())
