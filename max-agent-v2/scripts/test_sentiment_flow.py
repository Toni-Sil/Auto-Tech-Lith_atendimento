"""
Script to verify Sentiment Analysis Flow
Antigravity Skill: testing
"""
import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.ai_service import AIService
from app.infrastructure.database.supabase_client import SupabaseClient
from app.utils.logger import get_logger

logger = get_logger(__name__)

async def run_test():
    logger.info("Starting Sentiment Flow Verification...")
    
    ai_service = AIService()
    
    # Test 1: Negative Message
    print("\n--- TEST 1: NEGATIVE MESSAGE ---")
    neg_msg = "Estou muito irritado com o atendimento, nada funciona!"
    sender = "5511999999999"
    
    response = await ai_service.process_message(neg_msg, sender, "TestUser")
    print(f"AI Response: {response}")
    
    # Check Supabase
    supabase = SupabaseClient.get_client()
    client_data = supabase.table("dados cliente").select("*").eq("telefoneCliente", sender).execute()
    
    if client_data.data:
        client = client_data.data[0]
        print(f"Client Sentiment Score: {client.get('last_sentiment_score')}")
        print(f"Client History: {client.get('sentiment_history')}")
    else:
        print("Client not found in DB!")

    # Test 2: Positive Message
    print("\n--- TEST 2: POSITIVE MESSAGE ---")
    pos_msg = "Adorei o atendimento, muito obrigado por tudo!"
    
    response = await ai_service.process_message(pos_msg, sender, "TestUser")
    print(f"AI Response: {response}")
    
    client_data = supabase.table("dados cliente").select("*").eq("telefoneCliente", sender).execute()
    if client_data.data:
        print(f"Client Sentiment Score (Updated): {client_data.data[0].get('last_sentiment_score')}")

if __name__ == "__main__":
    asyncio.run(run_test())
