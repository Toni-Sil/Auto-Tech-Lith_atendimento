import sqlite3
import os

DB_PATH = "auto_tech_lith.db"

def fix_columns():
    if not os.path.exists(DB_PATH):
        print(f"Database {DB_PATH} not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Fix admin_users
    columns_to_add_admin = [
        ("email_verified", "BOOLEAN DEFAULT 0"),
        ("phone", "TEXT"),
        ("phone_verified", "BOOLEAN DEFAULT 0"),
        ("phone_otp", "TEXT"),
        ("telegram_username", "TEXT"),
        ("notification_preference", "TEXT DEFAULT 'email'"),
    ]

    cursor.execute("PRAGMA table_info(admin_users)")
    existing_columns_admin = [row[1] for row in cursor.fetchall()]

    for col_name, col_type in columns_to_add_admin:
        if col_name not in existing_columns_admin:
            try:
                cursor.execute(f"ALTER TABLE admin_users ADD COLUMN {col_name} {col_type}")
                print(f"Added column {col_name} to admin_users")
            except sqlite3.OperationalError as e:
                print(f"Failed to add column {col_name} to admin_users: {e}")

    # Fix tenants
    columns_to_add_tenant = [
        ("status", "VARCHAR DEFAULT 'pending'"),
    ]

    cursor.execute("PRAGMA table_info(tenants)")
    existing_columns_tenant = [row[1] for row in cursor.fetchall()]

    for col_name, col_type in columns_to_add_tenant:
        if col_name not in existing_columns_tenant:
            try:
                cursor.execute(f"ALTER TABLE tenants ADD COLUMN {col_name} {col_type}")
                # Important: Set existing tenants to 'active'
                cursor.execute("UPDATE tenants SET status = 'active' WHERE id = 1")
                print(f"Added column {col_name} to tenants")
            except sqlite3.OperationalError as e:
                print(f"Failed to add column {col_name} to tenants: {e}")

    # Fix audit_logs
    columns_to_add_audit = [
        ("operator_id", "INTEGER"),
        ("previous_value", "TEXT"),
        ("new_value", "TEXT"),
    ]

    cursor.execute("PRAGMA table_info(audit_logs)")
    existing_columns_audit = [row[1] for row in cursor.fetchall()]

    for col_name, col_type in columns_to_add_audit:
        if col_name not in existing_columns_audit:
            try:
                cursor.execute(f"ALTER TABLE audit_logs ADD COLUMN {col_name} {col_type}")
                print(f"Added column {col_name} to audit_logs")
            except sqlite3.OperationalError as e:
                print(f"Failed to add column {col_name} to audit_logs: {e}")

    conn.commit()
    conn.close()
    print("Database fix completed.")

if __name__ == "__main__":
    fix_columns()
