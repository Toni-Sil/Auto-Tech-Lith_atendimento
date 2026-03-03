import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.agents.admin_agent import AdminAgent
from src.models.customer import Customer

def run_async(coro):
    return asyncio.run(coro)

def test_admin_agent_denied_action():
    async def _test():
        with patch("src.agents.admin_agent.llm_service") as mock_llm_service, \
             patch("src.agents.admin_agent.async_session") as mock_db:
            
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session
            
            agent = AdminAgent()
            mock_llm_service.get_chat_response = AsyncMock()
            
            # Use AsyncMock for identify_user
            with patch.object(agent, 'identify_user', new_callable=AsyncMock) as mock_identify:
                mock_identify.return_value = "AUTHORIZED:TestOp:operator"
                
                # 2. Mock LLM
                tool_call = MagicMock()
                tool_call.function.name = "create_plan"
                tool_call.function.arguments = json.dumps({
                    "steps": [{"tool": "manage_customers", "action": "delete", "args": {"customer_id": 123}}]
                })
                tool_call.id = "call_123"
                
                llm_response = MagicMock()
                llm_response.tool_calls = [tool_call]
                llm_response.content = None
                
                # Side effect
                mock_llm_service.get_chat_response.side_effect = [llm_response, MagicMock(content="Ação negada.")]

                # 3. Exec
                response = await agent.process_message("Apague o cliente 123", context={"user_id": 1})
                
                # 4. Verify
                second_call_args = mock_llm_service.get_chat_response.call_args_list[1]
                tool_msg = second_call_args[0][0][-1]
                assert "❌ Ação negada" in tool_msg["content"]
    
    run_async(_test())

def test_admin_agent_needs_confirmation():
    async def _test():
        with patch("src.agents.admin_agent.llm_service") as mock_llm_service, \
             patch("src.agents.admin_agent.async_session") as mock_db:
            
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session
            
            agent = AdminAgent()
            mock_llm_service.get_chat_response = AsyncMock()

            # 1. Mock Identification (Admin)
            with patch.object(agent, 'identify_user', new_callable=AsyncMock) as mock_identify:
                mock_identify.return_value = "AUTHORIZED:TestAdmin:admin"
                
                # 2. Mock LLM
                tool_call = MagicMock()
                tool_call.function.name = "create_plan"
                tool_call.function.arguments = json.dumps({
                    "steps": [{"tool": "manage_customers", "action": "delete", "args": {"customer_id": 123}}]
                })
                tool_call.id = "call_456"
                
                llm_response = MagicMock()
                llm_response.tool_calls = [tool_call]
                llm_response.content = None
                
                mock_llm_service.get_chat_response.side_effect = [llm_response, MagicMock(content="Preciso de confirmação.")]

                # 3. Exec
                response = await agent.process_message("Apague o cliente 123", context={"user_id": 1})
                
                # 4. Verify
                second_call_args = mock_llm_service.get_chat_response.call_args_list[1]
                tool_msg = second_call_args[0][0][-1]
                assert "⚠️ Ação requer confirmação" in tool_msg["content"]
    
    run_async(_test())

def test_admin_agent_confirmed_action():
    async def _test():
        with patch("src.agents.admin_agent.llm_service") as mock_llm_service, \
             patch("src.agents.admin_agent.async_session") as mock_db:
            
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session
            
            agent = AdminAgent()
            mock_llm_service.get_chat_response = AsyncMock()

            with patch.object(agent, 'identify_user', new_callable=AsyncMock) as mock_identify:
                 mock_identify.return_value = "AUTHORIZED:TestAdmin:admin"
                
                 # 2. Mock LLM plan with DELETE
                 tool_call = MagicMock()
                 tool_call.function.name = "create_plan"
                 tool_call.function.arguments = json.dumps({
                     "steps": [{"tool": "manage_customers", "action": "delete", "args": {"customer_id": 123}}]
                 })
                 tool_call.id = "call_789"
                 
                 llm_response = MagicMock()
                 llm_response.tool_calls = [tool_call]
                 llm_response.content = None
                 
                 mock_llm_service.get_chat_response.side_effect = [llm_response, MagicMock(content="Feito.")]

                 # Mock DB: Find customer
                 mock_customer = MagicMock(spec=Customer)
                 mock_customer.name = "Test Customer"
                 mock_session.get.return_value = mock_customer

                 # 3. Process Message WITH CONFIRMATION
                 response = await agent.process_message("Sim, confirmar apagar cliente 123", context={"user_id": 1})
                 
                 # 4. Verify execution
                 second_call_args = mock_llm_service.get_chat_response.call_args_list[1]
                 tool_msg = second_call_args[0][0][-1]
                 
                 assert "deletado" in tool_msg["content"]
                 
                 # Verify DB calls
                 mock_session.get.assert_called()

    run_async(_test())
