"""
Verification Script for Smart Scheduling
Antigravity Skill: testing
"""
import asyncio
import sys
import os
from datetime import datetime

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.calendar_service import CalendarService
from app.utils.logger import get_logger

logger = get_logger(__name__)

async def test_scoring_logic():
    print("\n--- TEST: Scoring Logic ---")
    svc = CalendarService()
    
    # 1. Monday Morning (Should be neutral/low)
    date_mon = "2024-02-19" # Verify if this is a Monday
    print(f"Checking Monday ({date_mon})...")
    slots_mon = await svc.get_available_slots(date_mon)
    if "recommended" in slots_mon:
        print("Top 3 Monday Slots:")
        for s in slots_mon["recommended"]:
            print(f"  {s['time']} - Score: {s['score']}")

    # 2. Tuesday Afternoon (Should be High Score)
    date_tue = "2024-02-20" # Verify if this is a Tuesday
    print(f"\nChecking Tuesday ({date_tue})...")
    slots_tue = await svc.get_available_slots(date_tue)
    if "recommended" in slots_tue:
        print("Top 3 Tuesday Slots:")
        for s in slots_tue["recommended"]:
            print(f"  {s['time']} - Score: {s['score']}")
            
    # Verify Preference
    top_mon = slots_mon["recommended"][0]["score"] if slots_mon["recommended"] else 0
    top_tue = slots_tue["recommended"][0]["score"] if slots_tue["recommended"] else 0
    
    if top_tue > top_mon:
        print("\n✅ SUCCESS: Tuesday slots scored higher than Monday.")
    else:
        print("\n❌ FAILURE: Scoring logic might be off.")

async def run_tests():
    await test_scoring_logic()
    
if __name__ == "__main__":
    asyncio.run(run_tests())
