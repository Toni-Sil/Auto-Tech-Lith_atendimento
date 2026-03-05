
import sqlite3
import os

db_path = "auto_tech_lith.db"

def fix_schema():
    if not os.path.exists(db_path):
        print(f"Error: Database {db_path} not found.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check columns
    cursor.execute("PRAGMA table_info(admin_users);")
    columns = [row[1] for row in cursor.fetchall()]
    print(f"Current columns in 'admin_users': {columns}")

    missing_columns = {
        "avatar_url": "TEXT",
        "bio": "TEXT",
        "company_role": "TEXT"
    }

    for col, col_type in missing_columns.items():
        if col not in columns:
            print(f"Adding column '{col}'...")
            try:
                cursor.execute(f"ALTER TABLE admin_users ADD COLUMN {col} {col_type};")
                print(f"Column '{col}' added successfully.")
            except Exception as e:
                print(f"Error adding column '{col}': {e}")
        else:
            print(f"Column '{col}' already exists.")

    conn.commit()
    conn.close()
    print("Database fix completed.")

if __name__ == "__main__":
    fix_schema()
