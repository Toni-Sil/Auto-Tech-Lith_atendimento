"""
Verification Script for Validation & Tool Flow
Antigravity Skill: testing
"""
import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.validation_service import ValidationService
from app.services.client_service import ClientService
from app.services.ai_service import AIService
from app.utils.logger import get_logger

logger = get_logger(__name__)

async def test_validation_logic():
    print("\n--- TEST 1: Unit Validation Logic ---")
    vals = ValidationService()
    
    # Email
    emails = [("test@gmail.com", True), ("invalid-email", False), ("fake@nonexistentdomain12345.com", False)]
    for e, expected in emails:
        valid, msg = vals.validate_email(e)
        print(f"Email '{e}': {valid} (Expected: {expected}) - Msg: {msg}")

    # Phone
    phones = [("5511999999999", True), ("11999999999", True), ("123", False)]
    for p, expected in phones:
        valid, msg = vals.validate_phone(p)
        print(f"Phone '{p}': {valid} (Expected: {expected}) - Msg: {msg}")

async def test_client_service():
    print("\n--- TEST 2: Client Service Integration ---")
    svc = ClientService()
    
    # Invalid Data
    res = await svc.register_client({"name": "Jo", "phone": "123"})
    print(f"Invalid Register Result: {res}")
    
    # Valid Data
    valid_data = {
        "name": "Validation Test User",
        "phone": "5511988887777",
        "email": "test@gmail.com",
        "company": "Test Corp",
        "niche": "Technology"
    }
    res = await svc.register_client(valid_data)
    print(f"Valid Register Result: {res}")
    
    # Duplicate (Should Update)
    res = await svc.register_client(valid_data)
    print(f"Duplicate Register Result: {res}")

async def run_tests():
    await test_validation_logic()
    await test_client_service()
    
if __name__ == "__main__":
    asyncio.run(run_tests())
