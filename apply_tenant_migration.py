import sqlite3

def migrate_db():
    print("Starting multi-tenant database migration...")
    conn = sqlite3.connect("auto_tech_lith.db")
    cursor = conn.cursor()

    # 1. Create table manually if not created by SQLAlchemy yet
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tenants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name VARCHAR NOT NULL,
        subdomain VARCHAR UNIQUE,
        custom_domain VARCHAR UNIQUE,
        logo_url VARCHAR,
        primary_color VARCHAR,
        is_active BOOLEAN DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME
    );
    """)

    # 2. Insert Default Tenant
    cursor.execute("SELECT id FROM tenants WHERE id = 1")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO tenants (id, name, is_active) VALUES (1, 'Default Company', 1);")
        print("Inserted Default Tenant (id=1).")
    
    # 3. Tables to migrate
    tables = [
        "admin_users",
        "customers",
        "agent_profiles",
        "tickets",
        "meetings",
        "conversations",
        "webhook_configs",
        "recovery_requests",
        "system_config"
    ]

    for table in tables:
        # Check if tenant_id column exists
        cursor.execute(f"PRAGMA table_info({table})")
        columns = [col[1] for col in cursor.fetchall()]
        
        if "tenant_id" not in columns:
            try:
                # Add column
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN tenant_id INTEGER REFERENCES tenants(id);")
                # Update existing rows to belong to default tenant
                cursor.execute(f"UPDATE {table} SET tenant_id = 1;")
                print(f"Migrated table: {table}")
            except Exception as e:
                print(f"Error migrating table {table}: {e}")
        else:
            print(f"Table {table} already has tenant_id column.")

    conn.commit()
    conn.close()
    print("Migration completed successfully!")

if __name__ == "__main__":
    migrate_db()
