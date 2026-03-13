import asyncio
import os
import sys

sys.path.append(os.getcwd())

from src.agents.admin_agent import admin_agent


async def main():
    print("=== TEST START ===")

    # 1. Manage Customers
    print("\n--- Testing manage_customers ---")

    # Create
    fake_data = (
        '{"name": "Teste Bot", "phone": "5511999990000", "status": "em_processo"}'
    )
    res_create = await admin_agent.manage_customers(action="create", data=fake_data)
    print(f"CREATE: {res_create}")

    # Search
    res_search = await admin_agent.manage_customers(action="search", query="Teste Bot")
    print(f"SEARCH: {res_search}")

    # Extract ID from search (simple parse)
    try:
        cust_id = int(res_search.split("|")[0].replace("🆔", "").strip())

        # Update
        update_data = '{"status": "completed"}'
        res_update = await admin_agent.manage_customers(
            action="update", customer_id=cust_id, data=update_data
        )
        print(f"UPDATE: {res_update}")

        # 2. Manage Tickets
        print("\n--- Testing manage_tickets ---")
        res_ticket = await admin_agent.manage_tickets(
            action="create", customer_id=cust_id, subject="Ticket de Teste"
        )
        print(f"CREATE TICKET: {res_ticket}")

        res_list_tickets = await admin_agent.manage_tickets(
            action="list", customer_id=cust_id
        )
        print(f"LIST TICKETS: {res_list_tickets}")

        # 3. Manage Meetings
        print("\n--- Testing manage_meetings ---")
        res_meeting = await admin_agent.manage_meetings(
            action="schedule",
            customer_id=cust_id,
            date_str="2026-12-31",
            time_str="15:00",
        )
        print(f"SCHEDULE MEETING: {res_meeting}")

        res_list_meetings = await admin_agent.manage_meetings(action="list", days=30)
        print(f"LIST MEETINGS:\n{res_list_meetings}")

        # Clean up (Delete Customer)
        print("\n--- Testing DELETE Customer ---")
        res_delete = await admin_agent.manage_customers(
            action="delete", customer_id=cust_id
        )
        print(f"DELETE: {res_delete}")

    except Exception as e:
        print(f"ERROR: {e}")

    print("\n=== TEST END ===")


if __name__ == "__main__":
    asyncio.run(main())
