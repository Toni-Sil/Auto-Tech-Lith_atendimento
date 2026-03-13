import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from src.agents.base_agent import BaseAgent
from src.agents.tools import (AGENT_TOOLS, schedule_meeting,
                              update_customer_info)
from src.models.config_model import SystemConfig
from src.models.conversation import Conversation, MessageRole
from src.models.customer import Customer
from src.models.database import async_session
from src.services.evolution_service import EvolutionService
from src.services.llm_service import LLMService
from src.utils.logger import setup_logger

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
          - **Seja EXTREMAMENTE conciso e objetivo.**
          - Responda com frases curtas e diretas. Evite textos longos ou explicações desnecessárias.
          - Faça apenas UMA pergunta por vez se precisar de dados.
          - **RECUSE** educadamente qualquer assunto fora do escopo (piadas, clima, notícias, curiosidades). Diga apenas: "Não posso ajudar com isso. Vamos focar no seu atendimento?".
          - Não repita o que o cliente disse, vá direto para a solução ou próxima pergunta.

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

    async def get_or_create_customer(
        self, phone: str, name: Optional[str] = None, tenant_id: Optional[int] = None
    ) -> Customer:
        async with async_session() as session:
            stmt = select(Customer).where(Customer.phone == phone)
            if tenant_id:
                stmt = stmt.where(Customer.tenant_id == tenant_id)
            else:
                stmt = stmt.where(Customer.tenant_id == None)

            result = await session.execute(stmt)
            customer = result.scalar_one_or_none()

            if not customer:
                customer = Customer(
                    phone=phone, name=name or "Visitante", tenant_id=tenant_id
                )
                session.add(customer)
                await session.commit()
                await session.refresh(customer)

            return customer

    async def save_message(
        self,
        customer_id: int,
        role: MessageRole,
        content: str,
        tenant_id: Optional[int] = None,
    ):
        async with async_session() as session:
            msg = Conversation(
                customer_id=customer_id, role=role, content=content, tenant_id=tenant_id
            )
            session.add(msg)
            stmt = select(Customer).where(Customer.id == customer_id)
            result = await session.execute(stmt)
            customer = result.scalar_one()
            customer.last_interaction = datetime.now()

            await session.commit()

    async def load_system_prompt(self, customer: Customer, step: str) -> str:
        # Prioridade 1: Perfil ativo no banco (AgentProfile)
        try:
            from src.services.profile_service import profile_service

            active_profile = await profile_service.get_active_profile(
                tenant_id=customer.tenant_id
            )
            if active_profile and active_profile.base_prompt:
                logger.info(
                    f"Loading prompt from active profile: '{active_profile.name}' (id={active_profile.id})"
                )

                prompt_content = active_profile.base_prompt

                if customer.admin_instruction:
                    logger.info(
                        f"Injecting admin instruction for customer {customer.id}"
                    )
                    prompt_content = f"{prompt_content}\n\n🚩 **[INSTRUÇÃO PRIORITÁRIA DO ADMINISTRADOR]**: {customer.admin_instruction}\n(Siga esta instrução acima de qualquer outra regra se houver conflito)"

                try:
                    return prompt_content.format(
                        customer_name=customer.name or "Cliente",
                        customer_email=customer.email or "Não informado",
                        customer_company=customer.company or "Não informado",
                        current_step=step,
                        date_now=datetime.now().strftime("%d/%m/%Y %H:%M"),
                    )
                except KeyError:
                    return prompt_content
        except Exception as e:
            logger.warning(f"Could not load active agent profile: {e}")

        # Prioridade 2: system_prompt no SystemConfig
        db_prompt = None
        try:
            async with async_session() as session:
                config = await session.scalar(
                    select(SystemConfig).where(
                        SystemConfig.key == "system_prompt",
                        SystemConfig.tenant_id == customer.tenant_id,
                    )
                )
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
                    date_now=datetime.now().strftime("%d/%m/%Y %H:%M"),
                )
            except KeyError:
                return db_prompt

        # Prioridade 3: Prompt hardcoded (fallback final)
        return await self.get_system_prompt(
            {
                "customer_name": customer.name,
                "customer_email": customer.email,
                "customer_company": customer.company,
                "current_step": step,
            }
        )

    async def _get_conversation_history(
        self, customer_id: int, limit: int = 10
    ) -> List[Dict[str, str]]:
        messages = []
        async with async_session() as session:
            stmt = (
                select(Conversation)
                .where(Conversation.customer_id == customer_id)
                .order_by(Conversation.created_at.desc())
                .limit(limit)
            )

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
            from src.agents.tools import check_availability

            return await check_availability(tenant_id=customer.tenant_id, **arguments)
        else:
            return f"Erro: Ferramenta {function_name} desconhecida."

    async def _process_tool_calls(
        self, tool_calls: List[Any], customer: Customer
    ) -> List[Dict[str, Any]]:
        results = []
        for tool_call in tool_calls:
            result_content = await self._execute_tool(tool_call, customer)
            results.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result_content,
                }
            )
        return results

    async def _send_response(
        self,
        customer: Customer,
        response_text: str,
        phone: str,
        instance_name: Optional[str] = None,
    ):
        if not response_text:
            return

        MIN_DELAY = 8000
        MAX_DELAY = 10000
        char_delay = 15
        typing_delay = min(MIN_DELAY + len(response_text) * char_delay, MAX_DELAY)

        await self.save_message(
            customer.id,
            MessageRole.ASSISTANT,
            response_text,
            tenant_id=customer.tenant_id,
        )
        await self.evolution.send_message(
            phone, response_text, delay=typing_delay, instance_name=instance_name
        )

    async def process_message(self, message: str, context: dict) -> str:
        phone = context.get("phone")
        name = context.get("name")
        remote_jid = context.get("remote_jid", "")
        message_id = context.get("message_id", "")
        instance_name = context.get("instance_name")

        logger.info(f"Processing message from {phone}: {message}")

        # 1. Marcar mensagem como lida (✔✔ azul) — fire-and-forget
        if remote_jid and message_id:
            await self.evolution.mark_message_as_read(
                remote_jid, message_id, instance_name=instance_name
            )
            logger.info(
                f"Marked message {message_id} as read for {remote_jid} on {instance_name}"
            )

        # 2. Identificar Instância e Tenant — OBRIGATÓRIO para continuar
        tenant_id = None
        async with async_session() as session:
            from src.models.whatsapp import EvolutionInstance

            stmt = select(EvolutionInstance).where(
                EvolutionInstance.instance_name == instance_name
            )
            inst_obj = (await session.execute(stmt)).scalar_one_or_none()
            if inst_obj:
                tenant_id = inst_obj.tenant_id
                logger.info(
                    f"Instance {instance_name} associated with tenant_id={tenant_id}"
                )
            else:
                logger.warning(
                    f"Instance '{instance_name}' not found in DB. Blocking response — tenant not registered."
                )
                return ""

        # Bloquear se a instância existe mas não tem tenant associado
        if tenant_id is None:
            logger.warning(
                f"Instance '{instance_name}' has no tenant_id. Blocking response — tenant not configured."
            )
            return ""

        # 3. Identificar Cliente (escopado pelo tenant)
        customer = await self.get_or_create_customer(phone, name, tenant_id=tenant_id)

        # 4. Salvar mensagem do usuário
        await self.save_message(
            customer.id, MessageRole.USER, message, tenant_id=tenant_id
        )

        # 5. Ativar ícone 'digitando' ANTES do LLM
        await self.evolution.send_composing(
            phone, duration_ms=12000, instance_name=instance_name
        )

        # 6. Construir Contexto
        step = (
            "scheduling"
            if (customer.name and customer.name != "Visitante" and customer.email)
            else "initial_contact"
        )
        system_prompt = await self.load_system_prompt(customer, step)
        history = await self._get_conversation_history(customer.id)

        messages = [{"role": "system", "content": system_prompt}] + history

        if not messages or messages[-1].get("content") != message:
            messages.append({"role": "user", "content": message})

        # 7. Cache Redis
        response_text = None
        redis_client = None
        import hashlib

        tenant_str = str(tenant_id)
        cache_hash = hashlib.md5(
            (tenant_str + system_prompt + message).encode()
        ).hexdigest()
        cache_key = f"ai_response:{tenant_str}:{cache_hash}"

        try:
            import redis

            from src.config import settings

            redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD,
                db=0,
                decode_responses=True,
                socket_timeout=1,
            )
            cached = redis_client.get(cache_key)
            if cached:
                logger.info(f"🚀 Cache HIT para {cache_key}")
                await self._send_response(
                    customer, cached, phone, instance_name=instance_name
                )
                return cached
        except Exception as e:
            logger.warning(f"⚠️ Erro no cache Redis (ignorando): {e}")

        # 8. Chamar LLM
        response_msg = await self.llm.get_chat_response(messages, tools=self.tools)

        # 9. Processar Tool Calls
        if response_msg.tool_calls:
            logger.info(f"LLM requested tool calls: {len(response_msg.tool_calls)}")
            messages.append(response_msg)

            tool_results = await self._process_tool_calls(
                response_msg.tool_calls, customer
            )
            messages.extend(tool_results)

            final_response = await self.llm.get_chat_response(messages)
            response_text = final_response.content

            if not response_text:
                logger.info(
                    "Agent response empty after tool calls, forcing confirmation..."
                )
                messages.append(
                    {
                        "role": "system",
                        "content": "A tarefa foi realizada. Agora, por favor, envie uma mensagem curta e amigável ao cliente confirmando a ação realizada.",
                    }
                )
                final_response = await self.llm.get_chat_response(messages)
                response_text = (
                    final_response.content
                    or "Tarefa concluída com sucesso. Como posso ajudar mais?"
                )
        else:
            response_text = response_msg.content

        # 10. Salvar no Cache
        if response_text and redis_client:
            try:
                redis_client.setex(cache_key, 3600, response_text)
                logger.info(f"💾 Resposta salva no cache: {cache_key}")
            except Exception as e:
                logger.warning(f"⚠️ Erro ao salvar no Redis: {e}")

        # 11. Enviar Resposta
        await self._send_response(
            customer, response_text, phone, instance_name=instance_name
        )

        return response_text


customer_agent = CustomerServiceAgent()
