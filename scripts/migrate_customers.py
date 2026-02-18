import sqlite3
import os

db_path = "auto_tech_lith.db"

if not os.path.exists(db_path):
    print(f"Database file {db_path} not found!")
    exit(1)

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("ALTER TABLE customers ADD COLUMN status VARCHAR DEFAULT 'em_processo'")
    conn.commit()
    print("Migration successful: Added status column.")
except Exception as e:
    print(f"Error migrating: {e}")
finally:
    conn.close()
