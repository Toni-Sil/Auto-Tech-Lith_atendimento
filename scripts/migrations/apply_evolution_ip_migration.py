import sqlite3

def migrate_db():
    print("Starting Evolution Instances migration for IP and Email...")
    conn = sqlite3.connect("auto_tech_lith.db")
    cursor = conn.cursor()

    table = "evolution_instances"

    try:
        # Check if evolution_ip column exists
        cursor.execute(f"PRAGMA table_info({table})")
        columns = [col[1] for col in cursor.fetchall()]

        if "evolution_ip" not in columns:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN evolution_ip VARCHAR;")
            print(f"Added column evolution_ip to {table}")
        else:
            print(f"Column evolution_ip already exists in {table}")

        if "owner_email" not in columns:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN owner_email VARCHAR;")
            print(f"Added column owner_email to {table}")
        else:
            print(f"Column owner_email already exists in {table}")

        conn.commit()
        print("Migration completed successfully!")
    except Exception as e:
        print(f"Error during migration: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_db()
