"""
Test Notifications Logic
Antigravity Skill: automated-testing
"""
import asyncio
import sys
import os
from datetime import datetime, timedelta
from app.infrastructure.database.supabase_client import SupabaseClient
from app.tasks.notifications import check_briefing_reminders
from app.services.notification_service import NotificationService

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def setup_test_data():
    supabase = SupabaseClient.get_client()
    now = datetime.utcnow()
    
    # Clean up old test data if needed (optional)
    
    test_cases = [
        # 1. T-12h Appointment (should trigger 12h reminder)
        {
            "nome_cliente": "Teste 12h",
            "telefone_cliente": "5511999999999", # Mock
            "data_hora": (now + timedelta(hours=12)).isoformat(),
            "status": "confirmado",
            "tipo_reuniao": "briefing",
            "notification_12h_sent": False
        },
        # 2. T-6h Appointment (should trigger 6h reminder)
        {
            "nome_cliente": "Teste 6h",
            "telefone_cliente": "5511988888888",
            "data_hora": (now + timedelta(hours=6)).isoformat(),
            "status": "confirmado", 
            "tipo_reuniao": "briefing",
            "notification_6h_sent": False
        },
        # 3. T-1h Appointment (should trigger 1h reminder)
        {
            "nome_cliente": "Teste 1h",
            "telefone_cliente": "5511977777777",
            "data_hora": (now + timedelta(hours=1)).isoformat(),
            "status": "confirmado",
            "tipo_reuniao": "briefing",
            "notification_1h_sent": False
        },
         # 4. Already Sent (should NOT trigger)
        {
            "nome_cliente": "Teste Ja Enviado",
            "telefone_cliente": "5511966666666",
            "data_hora": (now + timedelta(hours=1)).isoformat(),
            "status": "confirmado",
            "tipo_reuniao": "briefing",
            "notification_1h_sent": True
        }
    ]
    
    ids = []
    print("--- Inserting Test Data ---")
    for case in test_cases:
        res = supabase.table("agendamentos").insert(case).execute()
        if res.data:
            print(f"Inserted: {res.data[0]['nome_cliente']} (ID: {res.data[0]['id']})")
            ids.append(res.data[0]['id'])
    return ids

async def run_test():
    # 1. Setup Data
    created_ids = await setup_test_data()
    
    # 2. Run Task
    print("\n--- Running Reminder Task ---")
    # We call the coroutine directly since we are in async context, 
    # bypassing Celery worker for the test.
    await check_briefing_reminders()
    
    # 3. Verify Results
    print("\n--- Verifying Results ---")
    supabase = SupabaseClient.get_client()
    
    for appt_id in created_ids:
        res = supabase.table("agendamentos").select("*").eq("id", appt_id).execute()
        if res.data:
            appt = res.data[0]
            name = appt['nome_cliente']
            
            if "12h" in name:
                print(f"[{name}] 12h Sent: {appt['notification_12h_sent']} (Expected: True)")
            elif "6h" in name:
                print(f"[{name}] 6h Sent: {appt['notification_6h_sent']} (Expected: True)")
            elif "1h" in name and "Ja Enviado" not in name:
                print(f"[{name}] 1h Sent: {appt['notification_1h_sent']} (Expected: True)")
            elif "Ja Enviado" in name:
                 print(f"[{name}] 1h Sent: {appt['notification_1h_sent']} (Expected: True - unchanged)")

    # 4. Cleanup
    print("\n--- Cleaning Up ---")
    for appt_id in created_ids:
        supabase.table("agendamentos").delete().eq("id", appt_id).execute()
    print("Done.")

if __name__ == "__main__":
    asyncio.run(run_test())
