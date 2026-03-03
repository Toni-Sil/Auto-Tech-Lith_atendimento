"""
Test Dashboard API
Antigravity Skill: testing
"""
import asyncio
import sys
import os
from pprint import pprint

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.api.dashboard.routes import get_kpis, get_leads, get_appointments, get_funnel

async def test_api():
    print("--- Testing Dashboard API ---")
    
    print("\n1. GET KPIs")
    try:
        kpis = await get_kpis()
        pprint(kpis)
    except Exception as e:
        print(f"Error: {e}")

    print("\n2. GET Leads (First 2)")
    try:
        leads = await get_leads()
        if isinstance(leads, list):
            print(f"Got {len(leads)} leads. First 2:")
            pprint(leads[:2])
        else:
            print(leads)
    except Exception as e:
        print(f"Error: {e}")

    print("\n3. GET Appointments (First 2)")
    try:
        appts = await get_appointments()
        if isinstance(appts, list):
            print(f"Got {len(appts)} appointments. First 2:")
            pprint(appts[:2])
        else:
            print(appts)
    except Exception as e:
        print(f"Error: {e}")

    print("\n4. GET Funnel")
    try:
        funnel = await get_funnel()
        pprint(funnel)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_api())
