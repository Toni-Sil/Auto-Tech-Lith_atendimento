
import sqlite3
import os

db_path = 'auto_tech_lith.db'
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, url, type, last_test_status FROM webhook_configs WHERE tenant_id IS NULL')
    rows = cursor.fetchall()
    for row in rows:
        print(f"ID: {row[0]} | Name: {row[1]} | URL: {row[2]} | Type: {row[3]} | Status: {row[4]}")
    conn.close()
else:
    print("DB not found")
