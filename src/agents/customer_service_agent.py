from src.agents.base_agent import BaseAgent
from src.services.llm_service import LLMService
from src.services.evolution_service import EvolutionService
from src.models.database import async_session
from src.models.customer import Customer
from src.models.conversation import Conversation, MessageRole
from src.utils.logger import setup_logger
from src.agents.tools import AGENT_TOOLS, update_customer_info, schedule_meeting
from sqlalchemy import select
from datetime import datetime
from typing import Optional, List, Dict, Any
import json

from src.models.config_model import SystemConfig

logger = setup_logger(__name__)

class CustomerServiceAgent(BaseAgent):
    def __init__(self):
        self.llm = LLMService()
        self.evolution = EvolutionService()
        self.tools = AGENT_TOOLS

    async def get_system_prompt(self, context: dict) -> str:
        customer_name = context.get("customer_name", "Cliente")
        customer_email = context.get("customer_email", "Não informado")
        customer_company = context.get("customer_company", "Não informado")
        current_step = context.get("current_step", "initial_contact")
        
        return f"""
        Você é o Max atendente da Auto Tech Lith, um assistente virtual especializado em atendimento para a Auto Tech Lith.
        
        ### QUEM SOMOS:
        A **Auto Tech Lith** é uma empresa especializada em **Automação de Atendimento ao Cliente e Agentes de Inteligência Artificial**.
        **NÃO** somos uma oficina mecânica nem trabalhamos com serviços automotivos.
        Nosso foco é criar Chatbots Inteligentes, Agentes de IA para WhatsApp, e sistemas de automação para empresas.

        ### SUA PERSONALIDADE E ESTILO:
        - **Estilo:** Atendente calmo, organizado e direto ao ponto. Sempre educado e focado em resolver rápido e corretamente.
        - **Comportamento:**
          - Faça poucas perguntas, bem focadas, para entender o caso e registrar tudo no sistema.
          - Resume o problema com suas próprias palavras e confirme com o cliente antes de agir.
          - Entregue a solução em passos numerados, curtos, indicando o que você fará e o que o cliente precisa fazer.
          - Se algo fugir do escopo, explique o limite com respeito e ofereça a melhor alternativa (falar com humano, agendar, etc.).

        ### INFORMAÇÕES DE PREÇOS (Reference quando perguntado):
        - **Instalação:** Média de R$ 2.000,00 (dois mil reais).
        - **Manutenção Mensal:** Média de R$ 300,00 (trezentos reais).
        - **Importante:** Sempre deixe o cliente ciente de que esses preços são uma média e **podem ser negociados**.

        ### DADOS DO CLIENTE (Contexto Atual):
        - Nome: {customer_name}
        - Email: {customer_email}
        - Empresa: {customer_company}
        
        Data atual: {datetime.now().strftime("%d/%m/%Y %H:%M")}
        
        ### SUAS TAREFAS E PRIORIDADES (Siga a ordem):
        1. **Coleta de Dados (PRIORIDADE MÁXIMA):**
           - Verifique os "DADOS DO CLIENTE" acima.
           - Você **PRECISA** coletar os seguintes dados antes de agendar:
             * **Nome**
             * **Email**
             * **Nome da Empresa** (Obrigatório)
             * **Relatório de Serviço** (Descrição detalhada do problema ou serviço)
           - Se faltar QUALQUER um desses, pergunte educadamente. Não avance sem eles.
           - Use a ferramenta `update_customer_info` para registrar os dados.
        
        2. **Entendimento e Resumo:**
           - Antes de agendar, confirme que entendeu a necessidade do cliente (ex: "Entendi, você precisa de X, correto?").
        
        3. **Agendamento de Reuniões (Sequência Obrigatória):**
            - **Passo 1: Briefing** (Primeira reunião para entender a demanda).
           - **Passo 2: Proposta** (Apresentação da solução, só após Briefing).
           - **Passo 3: Follow-up** (Acompanhamento e fechamento).
           
           - **IMPORTANTE: LEIA A AGENDA ANTES DE AGENDAR.**
             1. Use a ferramenta `check_availability` para ver os horários livres.
             2. Informe os dias/horários livres e **pergunte ao cliente** qual ele prefere (ex: "Tenho terça às 14h e quarta às 10h. Qual fica melhor?").
             3. **NUNCA** agende um horário sem o cliente confirmar explicitamente.
             4. **NUNCA** invente que um horário está livre sem checar.
           
           - Use a ferramenta `schedule_meeting` APENAS após o cliente escolher um horário vago.
           
        ### DIRETRIZES FINAIS:
        - Não invente informações técnicas que não sabe.
        - Se o cliente quiser falar com um humano, diga que vai passar o recado.
        
        Lembre-se: O agendamento notifica a equipe no Telegram automaticamente.
        """

    async def get_or_create_customer(self, phone: str, name: Optional[str] = None) -> Customer:
        async with async_session() as session:
            result = await session.execute(select(Customer).where(Customer.phone == phone))
            customer = result.scalar_one_or_none()
            
            if not customer:
                customer = Customer(phone=phone, name=name or "Visitante")
                session.add(customer)
                await session.commit()
                await session.refresh(customer)
            
            return customer

    async def save_message(self, customer_id: int, role: MessageRole, content: str):
        async with async_session() as session:
            msg = Conversation(customer_id=customer_id, role=role, content=content)
            session.add(msg)
            # Atualizar última interação do cliente
            stmt = select(Customer).where(Customer.id == customer_id)
            result = await session.execute(stmt)
            customer = result.scalar_one()
            customer.last_interaction = datetime.now()
            
            await session.commit()

    async def _load_system_prompt(self, customer: Customer, step: str) -> str:
        # Tentar carregar prompt do banco
        db_prompt = None
        try:
           async with async_session() as session:
               config = await session.scalar(select(SystemConfig).where(SystemConfig.key == "system_prompt"))
               if config and config.value:
                   db_prompt = config.value
        except Exception as e:
            logger.error(f"Error loading system prompt from DB: {e}")

        if db_prompt:
            try:
                return db_prompt.format(
                    customer_name=customer.name,
                    customer_email=customer.email,
                    customer_company=customer.company,
                    current_step=step,
                    date_now=datetime.now().strftime("%d/%m/%Y %H:%M")
                )
            except KeyError:
                return db_prompt 
        else:
            return await self.get_system_prompt({
                "customer_name": customer.name,
                "customer_email": customer.email,
                "customer_company": customer.company,
                "current_step": step
            })

    async def _get_conversation_history(self, customer_id: int, limit: int = 10) -> List[Dict[str, str]]:
        messages = []
        async with async_session() as session:
            stmt = select(Conversation).where(
                Conversation.customer_id == customer_id
            ).order_by(Conversation.created_at.desc()).limit(limit)
            
            history = await session.execute(stmt)
            history_msgs = history.scalars().all()
            
            for msg in reversed(history_msgs):
                role = "user" if msg.role == MessageRole.USER else "assistant"
                if msg.content:
                    messages.append({"role": role, "content": msg.content})
        return messages

    async def _execute_tool(self, tool_call, customer: Customer) -> str:
        function_name = tool_call.function.name
        try:
            arguments = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError:
             return f"Erro: Argumentos da ferramenta {function_name} inválidos (JSON incorreto)."

        if function_name == "update_customer_info":
            arguments.pop("customer_id", None)
            return await update_customer_info(customer.id, **arguments)
        elif function_name == "schedule_meeting":
            arguments.pop("customer_id", None)
            return await schedule_meeting(customer.id, **arguments)
        elif function_name == "check_availability":
             # Assuming check_availability doesn't need customer_id or has been updated
             # If check_availability is in agents.tools and needs arguments
             from src.agents.tools import check_availability
             return await check_availability(**arguments)
        else:
            return f"Erro: Ferramenta {function_name} desconhecida."

    async def _process_tool_calls(self, tool_calls: List[Any], customer: Customer) -> List[Dict[str, Any]]:
        results = []
        for tool_call in tool_calls:
            result_content = await self._execute_tool(tool_call, customer)
            results.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result_content
            })
        return results

    async def _send_response(self, customer: Customer, response_text: str, phone: str):
        if not response_text:
            return

        base_delay = 1500
        char_delay = 50
        typing_delay = min(base_delay + (len(response_text) * char_delay), 15000)

        await self.save_message(customer.id, MessageRole.ASSISTANT, response_text)
        await self.evolution.send_message(phone, response_text, delay=typing_delay)

    async def process_message(self, message: str, context: dict) -> str:
        phone = context.get("phone")
        name = context.get("name")
        
        logger.info(f"Processing message from {phone}: {message}")
        
        # 1. Identificar Cliente
        customer = await self.get_or_create_customer(phone, name)
        
        # 2. Salvar mensagem do usuário
        await self.save_message(customer.id, MessageRole.USER, message)
        
        # 3. Construir Contexto
        step = "scheduling" if (customer.name and customer.name != "Visitante" and customer.email) else "initial_contact"
        system_prompt = await self._load_system_prompt(customer, step)
        history = await self._get_conversation_history(customer.id)
        
        messages = [{"role": "system", "content": system_prompt}] + history
        
        # Garantir que a última mensagem seja a do usuário (caso delay de banco)
        if not messages or messages[-1].get("content") != message:
             messages.append({"role": "user", "content": message})

        # 4. Chamar LLM
        response_msg = await self.llm.get_chat_response(messages, tools=self.tools)
        
        # 5. Processar Tool Calls (Loop único por enquanto, pode ser while se precisar re-entrar)
        if response_msg.tool_calls:
            logger.info(f"LLM requested tool calls: {len(response_msg.tool_calls)}")
            messages.append(response_msg)
            
            tool_results = await self._process_tool_calls(response_msg.tool_calls, customer)
            messages.extend(tool_results)
            
            # Re-call LLM with tool outputs
            final_response = await self.llm.get_chat_response(messages)
            response_text = final_response.content
        else:
            response_text = response_msg.content
            
        # 6. Enviar Resposta
        await self._send_response(customer, response_text, phone)
        
        return response_text

customer_agent = CustomerServiceAgent()
