
import sqlite3

def check_counts():
    conn = sqlite3.connect('auto_tech_lith.db')
    cursor = conn.cursor()
    
    tables = ['system_config', 'vault_credentials', 'tenants', 'admin_users']
    for t in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {t}")
            count = cursor.fetchone()[0]
            print(f"Table {t}: {count} records")
        except Exception as e:
            print(f"Table {t} error: {e}")
            
    print("\n--- system_config Keys ---")
    try:
        cursor.execute("SELECT key, tenant_id FROM system_config")
        for row in cursor.fetchall():
            print(f"Key: {row[0]}, Tenant: {row[1]}")
    except Exception as e:
        print(f"Error: {e}")

    print("\n--- vault_credentials Services ---")
    try:
        cursor.execute("SELECT name, service_type, tenant_id FROM vault_credentials")
        for row in cursor.fetchall():
            print(f"Name: {row[0]}, Service: {row[1]}, Tenant: {row[2]}")
    except Exception as e:
        print(f"Error: {e}")

    conn.close()

if __name__ == "__main__":
    check_counts()
