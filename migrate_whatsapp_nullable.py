import sqlite3
import os

def migrate():
    db_file = 'auto_tech_lith.db'
    if not os.path.exists(db_file):
        print(f"Database {db_file} not found.")
        return

    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    print("Starting migration for evolution_instances...")

    try:
        # 1. Get current data
        cursor.execute("SELECT id, tenant_id, instance_name, phone_number, status, is_active, created_at, updated_at FROM evolution_instances")
        data = cursor.fetchall()

        # 2. Create new table schema (nullable tenant_id)
        # Note: We need to match the indices and foreign keys if they are critical, 
        # but for now let's focus on the NULL constraint.
        cursor.execute("DROP TABLE evolution_instances_backup")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE evolution_instances RENAME TO evolution_instances_old")
        
        cursor.execute("""
            CREATE TABLE evolution_instances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER,
                instance_name VARCHAR NOT NULL UNIQUE,
                phone_number VARCHAR,
                status VARCHAR DEFAULT 'pending',
                is_active BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
            )
        """)

        # 3. Copy data back
        cursor.execute("""
            INSERT INTO evolution_instances (id, tenant_id, instance_name, phone_number, status, is_active, created_at, updated_at)
            SELECT id, tenant_id, instance_name, phone_number, status, is_active, created_at, updated_at FROM evolution_instances_old
        """)

        # 4. Drop old table
        cursor.execute("DROP TABLE evolution_instances_old")

        conn.commit()
        print("✅ Migration successful: evolution_instances.tenant_id is now nullable.")

    except Exception as e:
        conn.rollback()
        print(f"❌ Error during migration: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
