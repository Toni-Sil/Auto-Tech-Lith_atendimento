import sqlite3
import os

DB_PATH = "auto_tech_lith.db"

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"Database {DB_PATH} not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Add columns to admin_users
    try:
        cursor.execute("ALTER TABLE admin_users ADD COLUMN email TEXT")
        cursor.execute("CREATE UNIQUE INDEX ix_admin_users_email ON admin_users (email)")
        print("Added email to admin_users")
    except sqlite3.OperationalError as e:
        print(f"Failed to add email: {e}")

    try:
        cursor.execute("ALTER TABLE admin_users ADD COLUMN recovery_token TEXT")
        print("Added recovery_token to admin_users")
    except sqlite3.OperationalError as e:
        print(f"Failed to add recovery_token: {e}")

    try:
        cursor.execute("ALTER TABLE admin_users ADD COLUMN recovery_token_expires_at DATETIME")
        print("Added recovery_token_expires_at to admin_users")
    except sqlite3.OperationalError as e:
        print(f"Failed to add recovery_token_expires_at: {e}")

    # Create recovery_requests table
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recovery_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                status TEXT DEFAULT 'pending',
                request_type TEXT NOT NULL,
                ip_address TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME NOT NULL,
                agent_approved_at DATETIME,
                FOREIGN KEY(admin_id) REFERENCES admin_users(id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_recovery_requests_admin_id ON recovery_requests (admin_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_recovery_requests_status ON recovery_requests (status)")
        print("Created recovery_requests table")
    except sqlite3.OperationalError as e:
        print(f"Failed to create recovery_requests: {e}")

    conn.commit()
    conn.close()
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
