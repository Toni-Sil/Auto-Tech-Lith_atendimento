import sqlite3
import os

db_path = "auto_tech_lith.db"

if not os.path.exists(db_path):
    print(f"Database file {db_path} not found!")
    exit(1)

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_config (
        key VARCHAR(50) PRIMARY KEY,
        value TEXT,
        is_secret BOOLEAN DEFAULT 0,
        description VARCHAR(200)
    )
    """)
    conn.commit()
    print("Migration successful: Created system_config table.")
except Exception as e:
    print(f"Error migrating: {e}")
finally:
    conn.close()
