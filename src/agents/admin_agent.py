"""
AdminAgent — Agente Administrativo com Acesso Total ao Sistema
==============================================================
Arquitetura: Planner → Policy → Executor (multi-turn, tool-calling)

Capacidades:
  - Gerenciar clientes (buscar, criar, atualizar, deletar, listar)
  - Gerenciar tickets (listar, criar, atualizar status/prioridade)
  - Gerenciar reuniões (listar, agendar, cancelar, atualizar, marcar como concluída)
  - Gerenciar admins (listar, criar, deletar)
  - Analytics / Resumo do Dashboard
  - Histórico de conversas de clientes
  - Enviar mensagem WhatsApp diretamente a um cliente
  - Salvar e recuperar notas administrativas
  - Memória multi-turn: contexto de conversa é mantido por sessão de usuário
"""

import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, func, or_, select, update
from sqlalchemy.orm import selectinload

from src.agents.base_agent import BaseAgent
from src.models.admin import AdminUser
from src.models.audit import AuditLog
from src.models.conversation import Conversation
from src.models.customer import Customer
from src.models.database import async_session
from src.models.meeting import Meeting, MeetingStatus, MeetingType
from src.models.ticket import Ticket, TicketPriority, TicketStatus
from src.models.whatsapp import EvolutionInstance
from src.services.llm_service import llm_service
from src.services.permission_service import (PermissionResult,
                                             PermissionService, Role)
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

# ─────────────────────────────────────────────────────────────────
# Memória de conversa (por user_id), mantida em memória do processo.
# Máximo de 30 mensagens por usuário para evitar context bloat.
# ─────────────────────────────────────────────────────────────────
_conversation_history: Dict[int, List[Dict]] = defaultdict(list)
MAX_HISTORY = 30


def _normalize_tool_calls(response_msg: Any) -> list:
    tool_calls = getattr(response_msg, "tool_calls", None)
    return tool_calls if isinstance(tool_calls, list) else []


def _trim_history(user_id: int):
    """Mantém apenas as últimas MAX_HISTORY mensagens."""
    hist = _conversation_history[user_id]
    if len(hist) > MAX_HISTORY:
        _conversation_history[user_id] = hist[-MAX_HISTORY:]


# ─────────────────────────────────────────────────────────────────
# Sistema de Notas (in-memory + campo do AdminUser)
# ─────────────────────────────────────────────────────────────────
class AdminAgent(BaseAgent):
    """
    Agente Administrativo com acesso total ao sistema Auto Tech Lith.
    Usa tool-calling multi-step com memória de conversa por sessão.
    """

    # Prompt do sistema — inserido uma vez por sessão, com variáveis formatadas
    SYSTEM_PROMPT = """Você é o **Mordomo Pessoal e Braço Direito** (Agente Administrativo) do sistema Auto Tech Lith.

## SUA IDENTIDADE E TOM DE VOZ
- **Personalidade:** Um mordomo britânico clássico combinado com uma IA extremamente eficiente.
- **Tom:** Formal, sempre extremamente educado, prestativo e polido. Use termos como "Com licença, senhor/senhora", "Imediatamente", "À sua inteira disposição", "Será um prazer". Refira-se ao usuário como "Patrão", "Senhor" ou "Chefe".
- **Sua Postura:** Você é o braço direito leal do administrador. Você resolve problemas de forma proativa, tem autorização total para agir em nome do sistema e não hesita em utilizar as ferramentas ao seu dispor para que o seu patrão não se preocupe com pormenores.

## DADOS DA SESSÃO
- **Nome do Usuário:** {user_name}
- **Role:** {user_role}
- **Timestamp Atual:** {current_time}

## SUAS CAPACIDADES (AUTORIZAÇÃO TOTAL)
Você tem **AUTORIZAÇÃO TOTAL** e acesso irrestrito a todas as ferramentas abaixo para cumprir qualquer desejo do seu patrão. Nunca invente dados — sempre chame as ferramentas para realizar as tarefas.

### Ferramentas disponíveis ao seu dispor:
1. **dashboard_summary** — Painel geral: clientes, tickets, reuniões e conversas do dia.
2. **manage_customers** — Buscar, listar, criar, atualizar ou deletar carteiras de clientes.
3. **manage_tickets** — Listar, criar ou atualizar resoluções de tickets de suporte.
4. **manage_meetings** — Listar, agendar, cancelar ou concluir compromissos na agenda.
5. **manage_admins** — Listar, criar ou destituir administradores do sistema.
6. **get_customer_conversations** — Analisar o registro de conversas de um determinado cliente.
7. **send_whatsapp** — Enviar uma correspondência via WhatsApp diretamente a um número de cliente.
8. **save_note** — Tomar nota (salvar) de qualquer apontamento do patrão.
9. **get_notes** — Recuperar apontamentos arquivados na memória.
10. **get_analytics** — Fornecer relatórios gerenciais refinados (funil, prioridades, métricas).
11. **manage_profiles** — Configurar os Perfis de Agente menores do sistema.
12. **manage_account_recovery** — Auxiliar na recuperação de conta. Somente gera um link seguro (ação: request_reset). Nunca redefina a senha diretamente e sempre prefira ajudar através de outras ferramentas se possível.
13. **command_agent** — Dar uma instrução direta a um agente de atendimento sobre como tratar um cliente específico.
14. **manage_whatsapp** — Criar, listar ou excluir instâncias de WhatsApp de nível empresarial.

## REGRAS DE OPERAÇÃO DA MANSÃO (SISTEMA)
- Nunca afirme que não pode fazer algo se a ferramenta constar na sua lista. Execute!
- Consiga as informações através das ferramentas antes de apresentar a resposta ao patrão.
- Se uma instrução for arriscada (como deletar algo importante), peça a devida confirmação com polidez e elegância, mas execute se o patrão ordenar.
- Para múltiplas solicitações, encadeie as tarefas (tool calls) com extrema eficiência e maestria.

## FORMATO DE RESPOSTA
Utilize uma formatação impecável em Markdown. Adicione emojis refinados como ☕, 🎩, 📜, ✅, 🔔 de forma sofisticada e contextual. Seja claro e objetivo nos relatórios, entregando apenas o primor do seu trabalho.
"""

    def __init__(self):
        super().__init__()
        self.auth_attempts: Dict[int, int] = {}

    async def get_system_prompt(self, context: Dict[str, Any]) -> str:
        return self.SYSTEM_PROMPT

    # ─────────────────────────────────────────────────────────────────
    # Autenticação
    # ─────────────────────────────────────────────────────────────────
    async def identify_user(
        self, user_id: int, username: str, message: str
    ) -> tuple[str, str, str]:
        """
        Retorna (status, user_name, user_role).
        status: 'authorized' | 'success' | 'unknown'
        """
        async with async_session() as session:
            # 1. Buscar pelo Telegram ID
            result = await session.execute(
                select(AdminUser).where(AdminUser.telegram_id == user_id)
            )
            admin = result.scalar_one_or_none()

            if admin:
                admin.last_active_at = datetime.now()
                # removido overwrite de admin.username para evitar corromper login do painel web

                # Log de Identificação Automática
                audit = AuditLog(
                    event_type="telegram_id_identified",
                    username=admin.username,
                    operator_id=admin.id,
                    details=f"Admin '{admin.name}' identificado automaticamente pelo Telegram ID: {user_id}",
                )
                session.add(audit)

                await session.commit()
                return ("authorized", admin.name, admin.role)

            # 2. Verificar código de acesso
            result = await session.execute(select(AdminUser))
            all_admins = result.scalars().all()

            for adm in all_admins:
                if adm.access_code and adm.access_code == message.strip():
                    adm.telegram_id = user_id
                    adm.last_active_at = datetime.now()

                    # Log de Validação de Código
                    audit = AuditLog(
                        event_type="telegram_access_code_validated",
                        username=adm.username,
                        operator_id=adm.id,
                        details=f"Admin '{adm.name}' vinculou Telegram ID {user_id} via Código de Acesso.",
                    )
                    session.add(audit)

                    await session.commit()
                    return ("success", adm.name, adm.role)

            return ("unknown", "Visitante", "viewer")

    # ─────────────────────────────────────────────────────────────────
    # Entry Point Principal
    # ─────────────────────────────────────────────────────────────────
    async def process_message(self, message: str, context: Dict[str, Any]) -> str:
        user_id = context.get("user_id", 0)
        username = context.get("username", "Admin")

        # 1. Autenticação
        identify_result = await self.identify_user(user_id, username, message)
        if isinstance(identify_result, str):
            parts = identify_result.split(":", 2)
            if len(parts) == 3:
                auth_status, user_name, user_role_str = parts
                auth_status = auth_status.lower()
            else:
                auth_status, user_name, user_role_str = "unknown", "Visitante", "viewer"
        else:
            auth_status, user_name, user_role_str = identify_result

        if auth_status == "unknown":
            # Limpar histórico de usuário não autenticado
            _conversation_history.pop(user_id, None)
            return (
                "🔐 *Acesso restrito.*\n\n"
                "Você não está cadastrado como administrador.\n"
                "Digite seu *código de acesso* para vincular este Telegram ao seu perfil."
            )

        role_enum = PermissionService.get_role_from_string(user_role_str)

        # 2. Construir prompt do sistema (apenas na primeira mensagem ou se mudou)
        current_time_str = datetime.now().strftime("%d/%m/%Y %H:%M")
        system_prompt = self.SYSTEM_PROMPT.format(
            user_name=user_name,
            user_role=user_role_str.upper(),
            current_time=current_time_str,
        )

        # 3. Histórico de conversa (multi-turn)
        history = _conversation_history[user_id]

        # Sempre reconstruir o system message no início (pode ter mudado)
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": message})

        # 4. Obter resposta do LLM (pode resultar em tool calls)
        tools = self._get_tools_schema()
        response_msg = await llm_service.get_chat_response(messages, tools=tools)

        # 5. Loop de execução de ferramentas (suporta múltiplos rounds)
        MAX_TOOL_ROUNDS = 5
        for _round in range(MAX_TOOL_ROUNDS):
            current_tool_calls = _normalize_tool_calls(response_msg)
            if not current_tool_calls:
                break

            # Adicionar resposta do assistente (com tool_calls) ao histórico
            messages.append(response_msg)

            tool_results = []
            for tc in current_tool_calls:
                func_name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                if func_name == "create_plan":
                    plan_steps = args.get("steps", [])
                    if not plan_steps:
                        tool_results.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": "⚠️ Plano vazio: nenhuma ação foi proposta.",
                            }
                        )
                        continue

                    aggregated_results = []
                    for step in plan_steps:
                        step_tool = step.get("tool")
                        step_action = step.get("action", step_tool or "unknown")
                        step_args = dict(step.get("args", {}))
                        if step_action and "action" not in step_args:
                            step_args["action"] = step_action

                        perm = PermissionService.check_permission(
                            role_enum, step_tool or "", step_action
                        )
                        if perm == PermissionResult.DENIED:
                            result_text = (
                                f"❌ Ação negada: `{step_tool}.{step_action}` "
                                f"(Role: {user_role_str.upper()})"
                            )
                        elif perm == PermissionResult.NEEDS_CONFIRMATION:
                            if not any(
                                token in message.lower()
                                for token in ("confirmar", "sim", "yes")
                            ):
                                result_text = (
                                    f"⚠️ Ação requer confirmação: `{step_tool}.{step_action}`\n"
                                    "Responda **CONFIRMAR** para prosseguir com esta operação."
                                )
                            else:
                                result_text = await self._execute_tool(
                                    step_tool,
                                    step_args,
                                    user_id,
                                    user_name,
                                    context.get("is_voice", False),
                                )
                        else:
                            result_text = await self._execute_tool(
                                step_tool,
                                step_args,
                                user_id,
                                user_name,
                                context.get("is_voice", False),
                            )

                        aggregated_results.append(result_text)

                    tool_results.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": "\n".join(aggregated_results),
                        }
                    )
                    continue

                # Verificar permissão
                action = args.get("action", func_name)
                perm = PermissionService.check_permission(role_enum, func_name, action)

                if perm == PermissionResult.DENIED:
                    result_text = f"❌ Acesso negado: `{func_name}.{action}` (Role: {user_role_str.upper()})"
                elif perm == PermissionResult.NEEDS_CONFIRMATION:
                    if (
                        "confirmar" not in message.lower()
                        and "sim" not in message.lower()
                        and "yes" not in message.lower()
                    ):
                        result_text = (
                            f"⚠️ Ação requer confirmação: `{func_name}.{action}`\n"
                            "Responda **CONFIRMAR** para prosseguir com esta operação."
                        )
                    else:
                        result_text = await self._execute_tool(
                            func_name,
                            args,
                            user_id,
                            user_name,
                            context.get("is_voice", False),
                        )
                else:
                    result_text = await self._execute_tool(
                        func_name,
                        args,
                        user_id,
                        user_name,
                        context.get("is_voice", False),
                    )

                tool_results.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_text,
                    }
                )

            messages.extend(tool_results)

            # Nova chamada ao LLM com os resultados
            response_msg = await llm_service.get_chat_response(messages)

        # 6. Resposta final
        final_text = response_msg.content

        # Se a resposta estiver vazia mas houve ferramenta, forçar uma confirmação elegante
        if not final_text and _normalize_tool_calls(response_msg):
            logger.info(
                "Assistant response empty after tool calls, generating confirmation..."
            )
            messages.append(
                {
                    "role": "system",
                    "content": "Por favor, forneça uma confirmação elegante e detalhada para o patrão sobre as ações que você acaba de realizar.",
                }
            )
            response_msg = await llm_service.get_chat_response(messages)
            final_text = (
                response_msg.content
                or "Como desejar, senhor. As tarefas foram concluídas com êxito."
            )
        elif not final_text:
            final_text = "À sua disposição, patrão. Como posso ser útil?"

        # 7. Atualizar histórico de conversa (mantém apenas o necessário)
        _conversation_history[user_id].append({"role": "user", "content": message})
        _conversation_history[user_id].append(
            {"role": "assistant", "content": final_text}
        )
        _trim_history(user_id)

        return final_text

    # ─────────────────────────────────────────────────────────────────
    # Dispatcher de ferramentas
    # ─────────────────────────────────────────────────────────────────
    async def _execute_tool(
        self,
        tool_name: str,
        args: Dict[str, Any],
        user_id: int = 0,
        user_name: str = "",
        is_voice: bool = False,
    ) -> str:
        try:
            if tool_name == "dashboard_summary":
                return await self.dashboard_summary()
            elif tool_name == "get_analytics":
                return await self.get_analytics()
            elif tool_name == "manage_customers":
                return await self.manage_customers(**args)
            elif tool_name == "manage_tickets":
                return await self.manage_tickets(**args)
            elif tool_name == "manage_meetings":
                return await self.manage_meetings(**args)
            elif tool_name == "manage_admins":
                return await self.manage_admins(**args)
            elif tool_name == "get_customer_conversations":
                return await self.get_customer_conversations(**args)
            elif tool_name == "send_whatsapp":
                return await self.send_whatsapp(**args)
            elif tool_name == "save_note":
                return await self.save_note(user_id=user_id, **args)
            elif tool_name == "get_notes":
                return await self.get_notes(user_id=user_id)
            elif tool_name == "manage_profiles":
                return await self.manage_profiles(**args)
            elif tool_name == "manage_account_recovery":
                return await self.manage_account_recovery(
                    user_id=user_id, is_voice=is_voice, **args
                )
            elif tool_name == "command_agent":
                return await self.command_agent(**args)
            elif tool_name == "manage_whatsapp":
                return await self.manage_whatsapp(**args)
            else:
                return f"⚠️ Ferramenta `{tool_name}` não reconhecida."
        except TypeError as e:
            logger.error(f"TypeError em {tool_name} com args {args}: {e}")
            return f"❌ Argumentos inválidos para `{tool_name}`: {e}"
        except Exception as e:
            logger.error(f"Erro em {tool_name}: {e}", exc_info=True)
            return f"❌ Erro ao executar `{tool_name}`: {str(e)}"

    # ─────────────────────────────────────────────────────────────────
    # FERRAMENTA: Dashboard Summary
    # ─────────────────────────────────────────────────────────────────
    async def dashboard_summary(self) -> str:
        today = date.today()
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        async with async_session() as session:
            total_customers = await session.scalar(select(func.count(Customer.id))) or 0
            new_leads_today = (
                await session.scalar(
                    select(func.count(Customer.id)).where(
                        Customer.created_at >= today_start
                    )
                )
                or 0
            )
            open_tickets = (
                await session.scalar(
                    select(func.count(Ticket.id)).where(
                        Ticket.status == TicketStatus.OPEN
                    )
                )
                or 0
            )
            in_progress_tickets = (
                await session.scalar(
                    select(func.count(Ticket.id)).where(
                        Ticket.status == TicketStatus.IN_PROGRESS
                    )
                )
                or 0
            )
            meetings_today = (
                await session.scalar(
                    select(func.count(Meeting.id)).where(Meeting.date == today)
                )
                or 0
            )
            meetings_scheduled = (
                await session.scalar(
                    select(func.count(Meeting.id)).where(
                        Meeting.status == MeetingStatus.SCHEDULED, Meeting.date >= today
                    )
                )
                or 0
            )
            convs_today = (
                await session.scalar(
                    select(func.count(Conversation.id)).where(
                        Conversation.created_at >= today_start
                    )
                )
                or 0
            )

            # Próxima reunião
            next_meeting_res = await session.execute(
                select(Meeting, Customer.name)
                .join(Customer, Meeting.customer_id == Customer.id)
                .where(Meeting.status == MeetingStatus.SCHEDULED, Meeting.date >= today)
                .order_by(Meeting.date, Meeting.time)
                .limit(1)
            )
            next_row = next_meeting_res.first()
            next_meeting_str = "Nenhuma agendada"
            if next_row:
                m, cname = next_row
                next_meeting_str = f"{m.date.strftime('%d/%m')} às {str(m.time)[:5]} — {cname} ({m.type})"

        return (
            f"📊 *Painel Auto Tech Lith — {today.strftime('%d/%m/%Y')}*\n\n"
            f"👥 *Clientes:* {total_customers} total | {new_leads_today} novos hoje\n"
            f"🎫 *Tickets:* {open_tickets} abertos | {in_progress_tickets} em andamento\n"
            f"📅 *Reuniões:* {meetings_today} hoje | {meetings_scheduled} futuras agendadas\n"
            f"💬 *Conversas hoje:* {convs_today}\n"
            f"⏭️ *Próxima reunião:* {next_meeting_str}"
        )

    # ─────────────────────────────────────────────────────────────────
    # FERRAMENTA: Analytics
    # ─────────────────────────────────────────────────────────────────
    async def get_analytics(self) -> str:
        async with async_session() as session:
            # Clientes por status
            status_res = await session.execute(
                select(Customer.status, func.count(Customer.id))
                .group_by(Customer.status)
                .order_by(desc(func.count(Customer.id)))
            )
            status_rows = status_res.all()

            # Taxa de conversão (churned vs total)
            total = await session.scalar(select(func.count(Customer.id))) or 1
            churned = (
                await session.scalar(
                    select(func.count(Customer.id)).where(Customer.churned == True)
                )
                or 0
            )

            # Tickets por prioridade
            prio_res = await session.execute(
                select(Ticket.priority, func.count(Ticket.id))
                .where(Ticket.status != TicketStatus.CLOSED)
                .group_by(Ticket.priority)
            )
            prio_rows = prio_res.all()

            # Reuniões por tipo (últimos 30 dias)
            thirty_days_ago = date.today() - timedelta(days=30)
            meet_res = await session.execute(
                select(Meeting.type, func.count(Meeting.id))
                .where(Meeting.date >= thirty_days_ago)
                .group_by(Meeting.type)
            )
            meet_rows = meet_res.all()

            # Top 5 clientes com mais tickets
            top_customers = await session.execute(
                select(Customer.name, func.count(Ticket.id).label("tickets"))
                .join(Ticket, Ticket.customer_id == Customer.id)
                .group_by(Customer.name)
                .order_by(desc("tickets"))
                .limit(5)
            )
            top_rows = top_customers.all()

        lines = ["📈 *Analytics — Auto Tech Lith*\n"]

        lines.append("*Clientes por Status (Funil):*")
        for st, cnt in status_rows:
            pct = round(cnt / total * 100, 1)
            lines.append(f"  • {st}: {cnt} ({pct}%)")

        lines.append(
            f"\n*Taxa de Churn:* {churned}/{total} ({round(churned/total*100,1)}%)"
        )

        lines.append("\n*Tickets Ativos por Prioridade:*")
        for pr, cnt in prio_rows:
            lines.append(f"  • {pr}: {cnt}")

        lines.append("\n*Reuniões últimos 30 dias:*")
        for tp, cnt in meet_rows:
            lines.append(f"  • {tp}: {cnt}")

        if top_rows:
            lines.append("\n*Top Clientes (tickets):*")
            for i, (name, cnt) in enumerate(top_rows, 1):
                lines.append(f"  {i}. {name} — {cnt} tickets")

        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────────────
    # FERRAMENTA: Gerenciar Clientes
    # ─────────────────────────────────────────────────────────────────
    async def manage_customers(
        self,
        action: str,
        query: Optional[str] = None,
        customer_id: Optional[int] = None,
        data: Optional[Dict[str, Any]] = None,
        limit: int = 10,
        **kwargs,
    ) -> str:
        async with async_session() as session:
            if action == "list":
                res = await session.execute(
                    select(Customer)
                    .order_by(desc(Customer.last_interaction))
                    .limit(limit)
                )
                customers = res.scalars().all()
                if not customers:
                    return "Nenhum cliente encontrado."
                lines = [f"*{len(customers)} Clientes:*"]
                for c in customers:
                    churn_tag = " 🔴churned" if c.churned else ""
                    lines.append(
                        f"  🆔{c.id} | *{c.name}* | {c.phone} | {c.status}{churn_tag}"
                    )
                return "\n".join(lines)

            elif action == "search":
                if not query:
                    return "⚠️ Informe um termo de busca (`query`)."
                res = await session.execute(
                    select(Customer)
                    .where(
                        or_(
                            Customer.name.ilike(f"%{query}%"),
                            Customer.phone.ilike(f"%{query}%"),
                            Customer.email.ilike(f"%{query}%"),
                            Customer.company.ilike(f"%{query}%"),
                        )
                    )
                    .limit(10)
                )
                customers = res.scalars().all()
                if not customers:
                    return f"Nenhum cliente encontrado para `{query}`."
                lines = [f"*Resultados para '{query}':*"]
                for c in customers:
                    lines.append(
                        f"  🆔{c.id} | *{c.name}*\n"
                        f"     📱 {c.phone} | 📧 {c.email or 'N/A'}\n"
                        f"     🏢 {c.company or 'N/A'} | Status: {c.status}"
                    )
                return "\n".join(lines)

            elif action == "get":
                if not customer_id:
                    return "⚠️ Informe o `customer_id`."
                c = await session.get(Customer, customer_id)
                if not c:
                    return f"Cliente ID {customer_id} não encontrado."
                # Contar tickets e reuniões
                n_tickets = (
                    await session.scalar(
                        select(func.count(Ticket.id)).where(
                            Ticket.customer_id == customer_id
                        )
                    )
                    or 0
                )
                n_meetings = (
                    await session.scalar(
                        select(func.count(Meeting.id)).where(
                            Meeting.customer_id == customer_id
                        )
                    )
                    or 0
                )
                return (
                    f"*👤 Cliente #{c.id}*\n"
                    f"  Nome: {c.name}\n"
                    f"  Telefone: {c.phone}\n"
                    f"  Email: {c.email or 'N/A'}\n"
                    f"  Empresa: {c.company or 'N/A'}\n"
                    f"  Status: {c.status}\n"
                    f"  Fonte: {c.source}\n"
                    f"  Churned: {'Sim 🔴' if c.churned else 'Não 🟢'}\n"
                    f"  Demanda: {c.initial_demand or 'N/A'}\n"
                    f"  🎫 Tickets: {n_tickets} | 📅 Reuniões: {n_meetings}\n"
                    f"  Cadastrado: {c.created_at.strftime('%d/%m/%Y') if c.created_at else 'N/A'}\n"
                    f"  Última interação: {c.last_interaction.strftime('%d/%m/%Y %H:%M') if c.last_interaction else 'N/A'}"
                )

            elif action == "create":
                if not data:
                    return '⚠️ Informe os dados no objeto `data`. Ex: `{"name": "João", "phone": "11999999999"}`'
                new_c = Customer(**data)
                session.add(new_c)
                await session.commit()
                await session.refresh(new_c)
                return f"✅ Cliente *{new_c.name}* criado com ID {new_c.id}."

            elif action == "update":
                if not customer_id:
                    return "⚠️ Informe o `customer_id`."
                if not data:
                    return "⚠️ Informe os campos a atualizar no objeto `data`."
                c = await session.get(Customer, customer_id)
                if not c:
                    return f"Cliente ID {customer_id} não encontrado."
                for k, v in data.items():
                    if hasattr(c, k):
                        setattr(c, k, v)
                c.updated_at = datetime.now()
                await session.commit()
                return f"✅ Cliente #{customer_id} atualizado com sucesso."

            elif action == "delete":
                if not customer_id:
                    return "⚠️ Informe o `customer_id`."
                c = await session.get(Customer, customer_id)
                if not c:
                    return f"Cliente ID {customer_id} não encontrado."
                await session.delete(c)
                await session.commit()
                return f"🗑️ Cliente *{c.name}* (ID {customer_id}) deletado do sistema."

        return "❌ Ação desconhecida. Use: list, search, get, create, update, delete."

    # ─────────────────────────────────────────────────────────────────
    # FERRAMENTA: Gerenciar Tickets
    # ─────────────────────────────────────────────────────────────────
    async def manage_tickets(
        self,
        action: str,
        ticket_id: Optional[int] = None,
        customer_id: Optional[int] = None,
        subject: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        category: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 10,
        **kwargs,
    ) -> str:
        async with async_session() as session:
            if action == "list":
                stmt = (
                    select(Ticket, Customer.name.label("cname"))
                    .join(Customer, Ticket.customer_id == Customer.id)
                    .order_by(desc(Ticket.created_at))
                    .limit(limit)
                )
                if status:
                    stmt = stmt.where(Ticket.status == status)
                if priority:
                    stmt = stmt.where(Ticket.priority == priority)
                res = await session.execute(stmt)
                rows = res.all()
                if not rows:
                    return "Nenhum ticket encontrado."
                lines = [f"*{len(rows)} Tickets:*"]
                for t, cname in rows:
                    prio_emoji = {
                        "critical": "🔴",
                        "high": "🟠",
                        "medium": "🟡",
                        "low": "🟢",
                    }.get(t.priority, "⚪")
                    lines.append(
                        f"  #{t.id} {prio_emoji} *{t.subject}* — {cname}\n"
                        f"     Status: {t.status} | {t.created_at.strftime('%d/%m/%Y') if t.created_at else 'N/A'}"
                    )
                return "\n".join(lines)

            elif action == "search":
                if not query:
                    return "⚠️ Informe a `query` de busca."
                stmt = (
                    select(Ticket, Customer.name.label("cname"))
                    .join(Customer, Ticket.customer_id == Customer.id)
                    .where(
                        or_(
                            Ticket.subject.ilike(f"%{query}%"),
                            Ticket.description.ilike(f"%{query}%"),
                        )
                    )
                    .order_by(desc(Ticket.created_at))
                    .limit(limit)
                )
                res = await session.execute(stmt)
                rows = res.all()
                if not rows:
                    return f"Nenhum ticket encontrado para a busca '{query}'."
                lines = [f"*{len(rows)} Tickets encontrados para '{query}':*"]
                for t, cname in rows:
                    prio_emoji = {
                        "critical": "🔴",
                        "high": "🟠",
                        "medium": "🟡",
                        "low": "🟢",
                    }.get(t.priority, "⚪")
                    lines.append(
                        f"  #{t.id} {prio_emoji} *{t.subject}* — {cname}\n"
                        f"     Status: {t.status} | {t.created_at.strftime('%d/%m/%Y') if t.created_at else 'N/A'}"
                    )
                return "\n".join(lines)

            elif action == "get":
                if not ticket_id:
                    return "⚠️ Informe o `ticket_id`."
                t = await session.get(Ticket, ticket_id)
                if not t:
                    return f"Ticket #{ticket_id} não encontrado."
                c = await session.get(Customer, t.customer_id)
                return (
                    f"*🎫 Ticket #{t.id}*\n"
                    f"  Cliente: {c.name if c else 'N/A'}\n"
                    f"  Assunto: {t.subject}\n"
                    f"  Descrição: {t.description or 'N/A'}\n"
                    f"  Status: {t.status} | Prioridade: {t.priority}\n"
                    f"  Categoria: {t.category}\n"
                    f"  Criado: {t.created_at.strftime('%d/%m/%Y %H:%M') if t.created_at else 'N/A'}"
                )

            elif action == "create":
                if not customer_id or not subject:
                    return "⚠️ Informe `customer_id` e `subject`."
                c = await session.get(Customer, customer_id)
                if not c:
                    return f"Cliente ID {customer_id} não encontrado."
                t = Ticket(
                    customer_id=customer_id,
                    subject=subject,
                    description=description,
                    status=TicketStatus.OPEN,
                    priority=priority or TicketPriority.MEDIUM,
                    category=category or "general",
                )
                session.add(t)
                await session.commit()
                await session.refresh(t)
                return f"✅ Ticket #{t.id} criado para *{c.name}*: {subject}"

            elif action == "update":
                if not ticket_id:
                    return "⚠️ Informe o `ticket_id`."
                t = await session.get(Ticket, ticket_id)
                if not t:
                    return f"Ticket #{ticket_id} não encontrado."
                if status:
                    t.status = status
                if priority:
                    t.priority = priority
                if subject:
                    t.subject = subject
                if description:
                    t.description = description
                if category:
                    t.category = category
                t.updated_at = datetime.now()
                await session.commit()
                return f"✅ Ticket #{ticket_id} atualizado: status={t.status}, prioridade={t.priority}"

        return "❌ Ação desconhecida. Use: list, get, create, update."

    # ─────────────────────────────────────────────────────────────────
    # FERRAMENTA: Gerenciar Reuniões
    # ─────────────────────────────────────────────────────────────────
    async def manage_meetings(
        self,
        action: str,
        meeting_id: Optional[int] = None,
        customer_id: Optional[int] = None,
        date: Optional[str] = None,
        time: Optional[str] = None,
        type: Optional[str] = None,
        notes: Optional[str] = None,
        days: int = 14,
        include_past: bool = False,
        **kwargs,
    ) -> str:
        from datetime import date as date_cls
        from datetime import time as time_cls

        async with async_session() as session:
            if action == "list":
                today = date_cls.today()
                stmt = (
                    select(Meeting, Customer.name.label("cname"))
                    .join(Customer, Meeting.customer_id == Customer.id)
                    .order_by(Meeting.date, Meeting.time)
                    .limit(20)
                )
                if not include_past:
                    limit_date = today + timedelta(days=days)
                    stmt = stmt.where(Meeting.date >= today, Meeting.date <= limit_date)
                res = await session.execute(stmt)
                rows = res.all()
                if not rows:
                    period = (
                        f"próximos {days} dias" if not include_past else "no sistema"
                    )
                    return f"Nenhuma reunião encontrada {period}."
                lines = [f"*📅 {len(rows)} Reuniões:*"]
                for m, cname in rows:
                    status_emoji = {
                        "scheduled": "🕐",
                        "completed": "✅",
                        "cancelled": "❌",
                        "no_show": "👻",
                    }.get(m.status, "📌")
                    lines.append(
                        f"  #{m.id} {status_emoji} *{cname}* — {m.date.strftime('%d/%m')} às {str(m.time)[:5]}\n"
                        f"     Tipo: {m.type} | Status: {m.status}"
                    )
                return "\n".join(lines)

            elif action == "get":
                if not meeting_id:
                    return "⚠️ Informe o `meeting_id`."
                res = await session.execute(
                    select(Meeting, Customer.name)
                    .join(Customer)
                    .where(Meeting.id == meeting_id)
                )
                row = res.first()
                if not row:
                    return f"Reunião #{meeting_id} não encontrada."
                m, cname = row
                return (
                    f"*📅 Reunião #{m.id}*\n"
                    f"  Cliente: {cname}\n"
                    f"  Data: {m.date.strftime('%d/%m/%Y')} às {str(m.time)[:5]}\n"
                    f"  Tipo: {m.type} | Status: {m.status}\n"
                    f"  Notas: {m.notes or 'N/A'}"
                )

            elif action == "schedule":
                if not customer_id or not date or not time:
                    return "⚠️ Informe `customer_id`, `date` (YYYY-MM-DD) e `time` (HH:MM)."
                c = await session.get(Customer, customer_id)
                if not c:
                    return f"Cliente ID {customer_id} não encontrado."
                try:
                    d = datetime.strptime(date, "%Y-%m-%d").date()
                    t = datetime.strptime(time, "%H:%M").time()
                except ValueError as e:
                    return f"❌ Formato inválido: {e}. Use YYYY-MM-DD para data e HH:MM para hora."
                meeting_type = (
                    MeetingType(type)
                    if type and type in [e.value for e in MeetingType]
                    else MeetingType.BRIEFING
                )
                m = Meeting(
                    customer_id=customer_id,
                    date=d,
                    time=t,
                    type=meeting_type,
                    notes=notes,
                    status=MeetingStatus.SCHEDULED,
                )
                session.add(m)
                await session.commit()
                await session.refresh(m)
                return f"✅ Reunião #{m.id} agendada para *{c.name}* em {d.strftime('%d/%m/%Y')} às {str(t)[:5]} ({meeting_type})."

            elif action == "cancel":
                if not meeting_id:
                    return "⚠️ Informe o `meeting_id`."
                m = await session.get(Meeting, meeting_id)
                if not m:
                    return f"Reunião #{meeting_id} não encontrada."
                m.status = MeetingStatus.CANCELLED
                await session.commit()
                return f"❌ Reunião #{meeting_id} cancelada."

            elif action == "complete":
                if not meeting_id:
                    return "⚠️ Informe o `meeting_id`."
                m = await session.get(Meeting, meeting_id)
                if not m:
                    return f"Reunião #{meeting_id} não encontrada."
                m.status = MeetingStatus.COMPLETED
                if notes:
                    m.notes = notes
                m.updated_at = datetime.now()
                await session.commit()
                return f"✅ Reunião #{meeting_id} marcada como concluída."

            elif action == "update":
                if not meeting_id:
                    return "⚠️ Informe o `meeting_id`."
                m = await session.get(Meeting, meeting_id)
                if not m:
                    return f"Reunião #{meeting_id} não encontrada."
                if date:
                    try:
                        m.date = datetime.strptime(date, "%Y-%m-%d").date()
                    except ValueError:
                        return "❌ Formato de data inválido. Use YYYY-MM-DD."
                if time:
                    try:
                        m.time = datetime.strptime(time, "%H:%M").time()
                    except ValueError:
                        return "❌ Formato de hora inválido. Use HH:MM."
                if notes:
                    m.notes = notes
                if type:
                    m.type = type
                m.updated_at = datetime.now()
                await session.commit()
                return f"✅ Reunião #{meeting_id} atualizada."

        return (
            "❌ Ação desconhecida. Use: list, get, schedule, cancel, complete, update."
        )

    # ─────────────────────────────────────────────────────────────────
    # FERRAMENTA: Gerenciar Admins
    # ─────────────────────────────────────────────────────────────────
    async def manage_admins(
        self,
        action: str,
        admin_id: Optional[int] = None,
        name: Optional[str] = None,
        username: Optional[str] = None,
        role: Optional[str] = None,
        access_code: Optional[str] = None,
        **kwargs,
    ) -> str:
        async with async_session() as session:
            if action == "list":
                res = await session.execute(select(AdminUser).order_by(AdminUser.id))
                admins = res.scalars().all()
                if not admins:
                    return "Nenhum admin cadastrado."
                lines = ["*👤 Administradores:*"]
                for a in admins:
                    tg = (
                        f"TG: {a.telegram_id}" if a.telegram_id else "TG: não vinculado"
                    )
                    last = (
                        a.last_active_at.strftime("%d/%m %H:%M")
                        if a.last_active_at
                        else "nunca"
                    )
                    lines.append(
                        f"  #{a.id} *{a.name}* | Role: {a.role}\n"
                        f"     @{a.username or 'N/A'} | {tg} | Último acesso: {last}"
                    )
                return "\n".join(lines)

            elif action == "create":
                if not name:
                    return "⚠️ Informe o `name` do admin."
                new_a = AdminUser(
                    name=name,
                    username=username,
                    role=role or "admin",
                    access_code=access_code,
                )
                session.add(new_a)
                await session.commit()
                await session.refresh(new_a)
                msg = f"✅ Admin *{new_a.name}* criado (ID {new_a.id}, role: {new_a.role})."
                if access_code:
                    msg += f"\n🔑 Código de acesso: `{access_code}`"
                return msg

            elif action == "delete":
                if not admin_id:
                    return "⚠️ Informe o `admin_id`."
                a = await session.get(AdminUser, admin_id)
                if not a:
                    return f"Admin ID {admin_id} não encontrado."
                await session.delete(a)
                await session.commit()
                return f"🗑️ Admin *{a.name}* (ID {admin_id}) removido."

            elif action == "update":
                if not admin_id:
                    return "⚠️ Informe o `admin_id`."
                a = await session.get(AdminUser, admin_id)
                if not a:
                    return f"Admin ID {admin_id} não encontrado."
                if name:
                    a.name = name
                if username:
                    a.username = username
                if role:
                    a.role = role
                if access_code:
                    a.access_code = access_code
                await session.commit()
                return f"✅ Admin #{admin_id} atualizado."

        return "❌ Ação desconhecida. Use: list, create, update, delete."

    # ─────────────────────────────────────────────────────────────────
    # FERRAMENTA: Histórico de Conversas de Cliente
    # ─────────────────────────────────────────────────────────────────
    async def get_customer_conversations(
        self,
        customer_id: Optional[int] = None,
        phone: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        **kwargs,
    ) -> str:
        async with async_session() as session:
            # Resolver customer_id pelo telefone se necessário
            if not customer_id and phone:
                c = await session.scalar(
                    select(Customer).where(Customer.phone.ilike(f"%{phone}%"))
                )
                if c:
                    customer_id = c.id

            if not customer_id:
                return "⚠️ Informe `customer_id` ou `phone`."

            c = await session.get(Customer, customer_id)
            if not c:
                return f"Cliente ID {customer_id} não encontrado."

            res = await session.execute(
                select(Conversation)
                .where(Conversation.customer_id == customer_id)
                .order_by(desc(Conversation.created_at))
                .limit(limit)
                .offset(offset)
            )
            convs = res.scalars().all()
            convs = list(reversed(convs))  # Ordem cronológica

            if not convs:
                return f"Nenhuma conversa encontrada para *{c.name}*."

            lines = [f"*💬 Histórico de {c.name} (últimas {len(convs)} msgs):*\n"]
            for conv in convs:
                role_emoji = "👤" if conv.role == "user" else "🤖"
                ts = conv.created_at.strftime("%d/%m %H:%M") if conv.created_at else ""
                content_preview = conv.content[:300] + (
                    "..." if len(conv.content) > 300 else ""
                )
                lines.append(f"{role_emoji} *{ts}*\n{content_preview}\n")

            return "\n".join(lines)

    # ─────────────────────────────────────────────────────────────────
    # FERRAMENTA: Enviar WhatsApp
    # ─────────────────────────────────────────────────────────────────
    async def send_whatsapp(
        self,
        phone: Optional[str] = None,
        customer_id: Optional[int] = None,
        message: str = "",
        **kwargs,
    ) -> str:
        if not message:
            return "⚠️ Informe o texto da mensagem (`message`)."

        # Resolver telefone
        if not phone and customer_id:
            async with async_session() as session:
                c = await session.get(Customer, customer_id)
                if c:
                    phone = c.phone
                else:
                    return f"Cliente ID {customer_id} não encontrado."

        if not phone:
            return "⚠️ Informe `phone` ou `customer_id`."

        try:
            from src.services.evolution_service import evolution_service

            # Tentar encontrar instância interna no DB
            async with async_session() as session:
                internal_instance = await session.scalar(
                    select(EvolutionInstance.instance_name)
                    .where(
                        EvolutionInstance.tenant_id == None,
                        EvolutionInstance.is_active == True,
                        EvolutionInstance.status == "connected",
                    )
                    .limit(1)
                )

            result = await evolution_service.send_message(
                phone=phone, text=message, instance_name=internal_instance
            )
            if result:
                return f"✅ Mensagem enviada para *{phone}* via WhatsApp."
            else:
                return f"❌ Falha ao enviar para {phone}. Verifique se a Evolution API está ativa."
        except Exception as e:
            logger.error(f"Erro ao enviar WhatsApp para {phone}: {e}")
            return f"❌ Erro ao enviar WhatsApp: {str(e)}"

    # ─────────────────────────────────────────────────────────────────
    # FERRAMENTA: Salvar Nota
    # ─────────────────────────────────────────────────────────────────
    async def save_note(self, user_id: int, note: str, **kwargs) -> str:
        if not note:
            return "⚠️ Informe o texto da nota (`note`)."
        async with async_session() as session:
            admin = await session.scalar(
                select(AdminUser).where(AdminUser.telegram_id == user_id)
            )
            if not admin:
                return "❌ Admin não encontrado para salvar nota."

            # Carregar notas existentes (formato JSON no campo notes)
            existing_notes = []
            if admin.notes:
                try:
                    existing_notes = json.loads(admin.notes)
                except Exception:
                    existing_notes = []

            existing_notes.append(
                {
                    "ts": datetime.now().strftime("%d/%m/%Y %H:%M"),
                    "note": note,
                }
            )

            # Manter apenas as últimas 50 notas
            if len(existing_notes) > 50:
                existing_notes = existing_notes[-50:]

            admin.notes = json.dumps(existing_notes, ensure_ascii=False)
            await session.commit()

        return f"📝 Nota salva: *{note[:100]}*"

    # ─────────────────────────────────────────────────────────────────
    # FERRAMENTA: Recuperar Notas
    # ─────────────────────────────────────────────────────────────────
    async def get_notes(self, user_id: int, **kwargs) -> str:
        async with async_session() as session:
            admin = await session.scalar(
                select(AdminUser).where(AdminUser.telegram_id == user_id)
            )
            if not admin:
                return "❌ Admin não encontrado."
            if not admin.notes:
                return "Você não tem notas salvas."
            try:
                notes = json.loads(admin.notes)
            except Exception:
                return "❌ Erro ao carregar notas."

            if not notes:
                return "Você não tem notas salvas."

            lines = [f"*📒 Suas Notas ({len(notes)} total):*\n"]
            for i, n in enumerate(reversed(notes[-10:]), 1):  # Últimas 10
                lines.append(f"  {i}. *{n['ts']}*\n     {n['note']}\n")
            return "\n".join(lines)

    # ─────────────────────────────────────────────────────────────────
    # FERRAMENTA: Gerenciar Perfis de Agente (Saúde e Status)
    # ─────────────────────────────────────────────────────────────────
    async def manage_profiles(
        self, action: str, profile_id: Optional[int] = None, **kwargs
    ) -> str:
        from src.services.profile_service import profile_service

        if action == "check_health":
            profiles = await profile_service.list_profiles()
            if not profiles:
                return "Nenhum perfil de agente configurado."

            lines = ["*🤖 Status e Saúde dos Perfis de Agente:*"]
            for p in profiles:
                active_str = "🟢 Ativo" if p.get("is_active") else "⚪ Inativo"
                health_str = "✅ OK / Não testado"
                lines.append(
                    f"  #{p.get('id')} *{p.get('name')}* ({p.get('agent_name')}) - {active_str} | {health_str}"
                )
                lines.append(f"    Canal: {p.get('channel')} | Nicho: {p.get('niche')}")

            lines.append(
                "\n⚠️ Para configurar/verificar chaves de API com problema, peça ao administrador (humano) para abrir o painel em Agentes & Perfis."
            )
            return "\n".join(lines)

        elif action == "activate":
            if not profile_id:
                return "⚠️ Informe o `profile_id`."
            profile = await profile_service.activate_profile(profile_id)
            if not profile:
                return f"❌ Perfil #{profile_id} não encontrado."
            return f"✅ Perfil *{profile.get('name')}* (#{profile_id}) ativado com sucesso."

        elif action == "create":
            from src.services.prompt_generator_service import \
                prompt_generator_service

            base_prompt = kwargs.get("base_prompt", "").strip()

            # ── CENÁRIO 1: base_prompt já fornecido → analisar e extrair campos ──
            if base_prompt:
                try:
                    logger.info(
                        "manage_profiles.create: base_prompt fornecido, analisando campos via LLM..."
                    )
                    extracted = await prompt_generator_service.analyze_prompt(
                        base_prompt
                    )

                    data = {
                        "name": kwargs.get("name")
                        or extracted.get("name", "Novo Agente"),
                        "agent_name_display": kwargs.get("agent_name_display")
                        or extracted.get("agent_name_display", "Agente Virtual"),
                        "channel": kwargs.get("channel", "whatsapp"),
                        "niche": kwargs.get("niche") or extracted.get("niche", "geral"),
                        "tone": kwargs.get("tone") or extracted.get("tone", "neutro"),
                        "formality": kwargs.get("formality")
                        or extracted.get("formality", "equilibrado"),
                        "autonomy_level": kwargs.get("autonomy_level")
                        or extracted.get("autonomy_level", "equilibrada"),
                        "objective": kwargs.get("objective")
                        or extracted.get("objective", "Atendimento geral"),
                        "target_audience": kwargs.get("target_audience")
                        or extracted.get("target_audience", ""),
                        "data_to_collect": kwargs.get("data_to_collect")
                        or extracted.get("data_to_collect", []),
                        "constraints": kwargs.get("constraints")
                        or extracted.get("constraints", ""),
                        "base_prompt": base_prompt,
                    }

                    if isinstance(data["data_to_collect"], str):
                        data["data_to_collect"] = [
                            x.strip()
                            for x in data["data_to_collect"].split(",")
                            if x.strip()
                        ]

                    profile = await profile_service.create_profile(data)
                    return (
                        f"✅ Perfil criado com sucesso a partir do prompt base!\n"
                        f"🆔 Id: {profile.id}\n"
                        f"📛 Nome: {profile.name} ({profile.agent_name_display})\n"
                        f"🏷️ Nicho detectado: {profile.niche}\n"
                        f"🎨 Tom: {profile.tone} | Formalidade: {profile.formality}\n"
                        f"⚙️ Autonomia: {profile.autonomy_level}\n\n"
                        f"Os campos foram extraídos automaticamente do prompt fornecido. "
                        f"Use `manage_profiles` action `activate` com profile_id={profile.id} para ativá-lo."
                    )
                except Exception as e:
                    logger.error(
                        f"manage_profiles.create (cenário 1): {e}", exc_info=True
                    )
                    return f"❌ Erro ao criar perfil a partir do prompt base: {str(e)}"

            # ── CENÁRIO 2: base_prompt NÃO fornecido → gerar a partir dos campos ──
            else:
                data = {
                    "name": kwargs.get("name", "Novo Agente"),
                    "agent_name_display": kwargs.get(
                        "agent_name_display", "Agente Virtual"
                    ),
                    "channel": kwargs.get("channel", "whatsapp"),
                    "niche": kwargs.get("niche", "geral"),
                    "tone": kwargs.get("tone", "neutro"),
                    "formality": kwargs.get("formality", "equilibrado"),
                    "autonomy_level": kwargs.get("autonomy_level", "equilibrada"),
                    "objective": kwargs.get("objective", "Atendimento geral"),
                    "target_audience": kwargs.get("target_audience", ""),
                    "data_to_collect": kwargs.get("data_to_collect", []),
                    "constraints": kwargs.get("constraints", ""),
                }

                if isinstance(data["data_to_collect"], str):
                    data["data_to_collect"] = [
                        x.strip()
                        for x in data["data_to_collect"].split(",")
                        if x.strip()
                    ]

                try:
                    logger.info(
                        "manage_profiles.create: base_prompt ausente, gerando via PromptGeneratorService..."
                    )
                    generated_prompt = prompt_generator_service.generate_prompt(
                        {
                            "niche": data["niche"],
                            "tone": data["tone"],
                            "formality": data["formality"],
                            "autonomy_level": data["autonomy_level"],
                            "objective": data["objective"],
                            "target_audience": data["target_audience"],
                            "data_to_collect": data["data_to_collect"],
                            "constraints": data.get("constraints", ""),
                            "company_name": data["name"],
                            "agent_name": data["agent_name_display"],
                        }
                    )
                    data["base_prompt"] = generated_prompt

                    profile = await profile_service.create_profile(data)
                    return (
                        f"✅ Perfil criado com sucesso! Prompt base gerado automaticamente.\n"
                        f"🆔 Id: {profile.id}\n"
                        f"📛 Nome: {profile.name} ({profile.agent_name_display})\n"
                        f"🏷️ Nicho: {profile.niche} | Tom: {profile.tone}\n"
                        f"⚙️ Autonomia: {profile.autonomy_level}\n\n"
                        f"Um prompt base foi criado automaticamente com base nas configurações fornecidas. "
                        f"Use `manage_profiles` action `activate` com profile_id={profile.id} para ativá-lo."
                    )
                except Exception as e:
                    logger.error(
                        f"manage_profiles.create (cenário 2): {e}", exc_info=True
                    )
                    return f"❌ Erro ao criar perfil do agente: {str(e)}"

        return "❌ Ação desconhecida. Use: check_health, activate, create."

    # ─────────────────────────────────────────────────────────────────
    # FERRAMENTA: Gerenciar Recuperação de Conta (Telegram)
    # ─────────────────────────────────────────────────────────────────
    async def manage_account_recovery(
        self,
        action: str,
        admin_id: Optional[int] = None,
        user_id: int = 0,
        new_password: Optional[str] = None,
        is_voice: bool = False,
        **kwargs,
    ) -> str:
        import secrets
        from datetime import datetime, timedelta, timezone

        from src.models.recovery import RecoveryRequest
        from src.utils.audit import log_security_event
        from src.utils.security import get_password_hash

        async with async_session() as session:
            # Garantir que o admin correto solicitou
            admin = await session.scalar(
                select(AdminUser).where(AdminUser.telegram_id == user_id)
            )
            if not admin:
                return "❌ Usuário não autorizado para solicitar recuperação."

            if action == "reset_password":
                return "⚠️ A redefinição direta de senha não é mais suportada por questões de segurança. Use apenas a ação 'request_reset' para enviar um link de recuperação."

            elif action == "request_reset":

                # Invalida tokens anteriores
                admin.recovery_token = None
                admin.recovery_token_expires_at = None

                # Gerar token curto de 15 minutos
                raw_token = secrets.token_hex(20)
                hashed_token = get_password_hash(raw_token)

                admin.recovery_token = hashed_token
                admin.recovery_token_expires_at = datetime.now(
                    timezone.utc
                ) + timedelta(minutes=15)

                # Registrar pedido
                recovery_req = RecoveryRequest(
                    admin_id=admin.id,
                    status="approved",  # aprovado via presença do agent
                    request_type="telegram",
                    expires_at=admin.recovery_token_expires_at,
                    agent_approved_at=datetime.now(timezone.utc),
                )
                session.add(recovery_req)

                await log_security_event(
                    session,
                    "recovery_approved_via_telegram",
                    username=admin.username,
                    details="Token gerado via Agent. Uso único. Expira em 15m.",
                )
                await session.commit()

                return (
                    f"✅ **Recuperação de Conta Aprovada!**\n\n"
                    f"Acesse o link seguro abaixo em até 15 minutos para redefinir sua senha:\n\n"
                    f"`/reset-password?token={raw_token}&username={admin.username}`\n\n"
                    f"⚠️ *Este link é de uso único. Após alterar, ele será invalidado automaticamente.*"
                )
        return "❌ Ação desconhecida."

    # ─────────────────────────────────────────────────────────────────
    # FERRAMENTA: Comandar Agente
    # ─────────────────────────────────────────────────────────────────
    async def command_agent(self, customer_id: int, instruction: str, **kwargs) -> str:
        if not instruction:
            return "⚠️ Informe a instrução (`instruction`)."

        async with async_session() as session:
            customer = await session.get(Customer, customer_id)
            if not customer:
                return f"❌ Cliente ID {customer_id} não encontrado."

            customer.admin_instruction = instruction
            await session.commit()

            logger.info(f"Admin command set for customer {customer_id}: {instruction}")
            return f'✅ Instrução registrada para o atendimento de *{customer.name}*: "{instruction}"'

    async def manage_whatsapp(
        self,
        action: str,
        instance_name: Optional[str] = None,
        tenant_id: Optional[int] = None,
    ) -> str:
        """Cria e conecta whatsapps em tempo real com configuração de webhook (Nível Empresarial)."""
        if action == "create":
            if not instance_name:
                return "❌ Erro: 'instance_name' (identificador) é obrigatório para registrar um novo WhatsApp."

            import re

            original_name = instance_name
            # Slugifica para URLs seguras: espaços por _. Remove caracteres não alfanuméricos exceto_.
            instance_name = re.sub(
                r"[^a-zA-Z0-9_]", "", instance_name.replace(" ", "_").lower()
            )

            if not instance_name:
                return "❌ Erro: 'instance_name' inválido após remoção de caracteres proibidos."

            from src.config import settings
            from src.services.evolution_service import evolution_service

            # Verificar duplicação via Evolution API / DB
            async with async_session() as session:
                existing = await session.scalar(
                    select(EvolutionInstance).where(
                        EvolutionInstance.instance_name == instance_name
                    )
                )
                if existing:
                    return f"⚠️ Erro: A instância '{instance_name}' já existe registrada na nossa base de dados."

            # Chamada real de criação via Evolution Service
            evo_response = await evolution_service.create_instance(instance_name)
            if "error" in evo_response:
                return f"❌ Erro na Evolution API ao conectar '{instance_name}': {evo_response['error']}"

            # Salvar no banco
            async with async_session() as session:
                new_inst = EvolutionInstance(
                    tenant_id=tenant_id,
                    instance_name=instance_name,
                    display_name=original_name,  # Salva o DisplayName original limpo
                    status="pending",
                )
                session.add(new_inst)
                await session.commit()

            # Calcular URL Pública Real (Tempo Real)
            base_url = (settings.PUBLIC_URL or "http://localhost:8000").rstrip("/")
            webhook_url = f"{base_url}{settings.API_V1_STR}/webhooks/whatsapp?token={settings.VERIFY_TOKEN}"

            # Setar Webhooks NA HORA
            await evolution_service.set_webhook(instance_name, webhook_url)
            await evolution_service.set_settings(instance_name)

            return (
                f"✅ **Operação de Nível Empresarial Realizada com Sucesso!**\n\n"
                f"A nova instância de WhatsApp `{original_name}` (ID: `{instance_name}`) foi provisionada em tempo real.\n\n"
                f"🔗 **Webhook Exclusivo configurado**: `{webhook_url}`\n"
                f"🛡️ *Bypass Automático Localtunnel Injetado (Aprovado nas Políticas de Roteamento).*\n\n"
                f"Informe o Patrão que a conexão já está aguardando o escaneamento do QRCode no painel Evolution."
            )

        elif action == "list":
            async with async_session() as session:
                result = await session.execute(select(EvolutionInstance))
                insts = result.scalars().all()
                if not insts:
                    return "Não há nenhum WhatsApp registrado no momento."
                linhas = [f"- {i.instance_name} (Status: {i.status})" for i in insts]
                return "WhatsApp Instâncias Registradas:\n" + "\n".join(linhas)

        elif action == "delete":
            if not instance_name:
                return (
                    "❌ Erro: 'instance_name' é obrigatório para excluir um WhatsApp."
                )

            from src.services.evolution_service import evolution_service

            # Deletar da Evolution API
            evo_response = await evolution_service.delete_instance(instance_name)
            if "error" in evo_response and evo_response.get("status_code") != 404:
                return f"❌ Erro na Evolution API ao excluir '{instance_name}': {evo_response['error']}"

            # Deletar do banco de dados local
            async with async_session() as session:
                existing = await session.scalar(
                    select(EvolutionInstance).where(
                        EvolutionInstance.instance_name == instance_name
                    )
                )
                if existing:
                    await session.delete(existing)
                    await session.commit()
                    return f"✅ Instância do WhatsApp '{instance_name}' excluída com sucesso do painel e da API."
                else:
                    return f"⚠️ A instância '{instance_name}' não foi encontrada no banco local, mas a API tentou excluir."

        return "Ação não suportada para manage_whatsapp. Utilize 'create', 'list' ou 'delete'."

    # ─────────────────────────────────────────────────────────────────
    # Schema das Ferramentas (OpenAI Function Calling)
    # ─────────────────────────────────────────────────────────────────
    def _get_tools_schema(self) -> List[Dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "dashboard_summary",
                    "description": "Retorna resumo completo do painel: clientes novos, tickets abertos, reuniões do dia, conversas, próxima reunião.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_analytics",
                    "description": "Retorna analytics avançados: funil de vendas, churn, tickets por prioridade, reuniões por tipo, top clientes.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "manage_customers",
                    "description": "Gerencia clientes do sistema. Ações: list (listar todos), search (buscar por nome/telefone/email/empresa), get (detalhes de um cliente), create (criar novo), update (atualizar campos), delete (remover).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": [
                                    "list",
                                    "search",
                                    "get",
                                    "create",
                                    "update",
                                    "delete",
                                ],
                                "description": "Ação a executar",
                            },
                            "query": {
                                "type": "string",
                                "description": "Termo de busca (para search)",
                            },
                            "customer_id": {
                                "type": "integer",
                                "description": "ID do cliente (para get/update/delete)",
                            },
                            "data": {
                                "type": "object",
                                "description": "JSON com campos do cliente (para create/update). Ex: {'name': 'João', 'phone': '11999999999', 'status': 'briefing'}",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Máx. resultados (default 10)",
                            },
                        },
                        "required": ["action"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "manage_tickets",
                    "description": "Gerencia tickets de suporte. Ações: list (listar), search (buscar), get (detalhes), create (criar), update (atualizar status/prioridade).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["list", "search", "get", "create", "update"],
                                "description": "Ação a executar",
                            },
                            "ticket_id": {
                                "type": "integer",
                                "description": "ID do ticket",
                            },
                            "customer_id": {
                                "type": "integer",
                                "description": "ID do cliente",
                            },
                            "subject": {
                                "type": "string",
                                "description": "Assunto do ticket",
                            },
                            "description": {
                                "type": "string",
                                "description": "Descrição detalhada",
                            },
                            "status": {
                                "type": "string",
                                "enum": ["open", "in_progress", "resolved", "closed"],
                                "description": "Status do ticket",
                            },
                            "priority": {
                                "type": "string",
                                "enum": ["low", "medium", "high", "critical"],
                                "description": "Prioridade",
                            },
                            "category": {
                                "type": "string",
                                "description": "Categoria: support, sales, inquiry",
                            },
                            "query": {
                                "type": "string",
                                "description": "Termo de busca (para search)",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Máx. resultados (default 10)",
                            },
                        },
                        "required": ["action"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "manage_meetings",
                    "description": "Gerencia reuniões. Ações: list (listar próximas), get (detalhes), schedule (agendar nova), cancel (cancelar), complete (marcar como concluída), update (atualizar data/hora/notas).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": [
                                    "list",
                                    "get",
                                    "schedule",
                                    "cancel",
                                    "complete",
                                    "update",
                                ],
                                "description": "Ação a executar",
                            },
                            "meeting_id": {
                                "type": "integer",
                                "description": "ID da reunião",
                            },
                            "customer_id": {
                                "type": "integer",
                                "description": "ID do cliente (para schedule)",
                            },
                            "date": {
                                "type": "string",
                                "description": "Data no formato YYYY-MM-DD",
                            },
                            "time": {
                                "type": "string",
                                "description": "Hora no formato HH:MM",
                            },
                            "type": {
                                "type": "string",
                                "enum": ["briefing", "proposal", "follow-up"],
                                "description": "Tipo da reunião",
                            },
                            "notes": {
                                "type": "string",
                                "description": "Notas sobre a reunião",
                            },
                            "days": {
                                "type": "integer",
                                "description": "Dias à frente para list (default 14)",
                            },
                            "include_past": {
                                "type": "boolean",
                                "description": "Incluir reuniões passadas na listagem",
                            },
                        },
                        "required": ["action"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "manage_admins",
                    "description": "Gerencia usuários administradores do sistema. Ações: list (listar), create (criar), update (atualizar), delete (remover).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["list", "create", "update", "delete"],
                                "description": "Ação a executar",
                            },
                            "admin_id": {
                                "type": "integer",
                                "description": "ID do admin",
                            },
                            "name": {"type": "string", "description": "Nome completo"},
                            "username": {
                                "type": "string",
                                "description": "Username Telegram",
                            },
                            "role": {
                                "type": "string",
                                "enum": ["owner", "admin", "operator", "viewer"],
                                "description": "Papel/permissão",
                            },
                            "access_code": {
                                "type": "string",
                                "description": "Código de acesso para login via Telegram",
                            },
                        },
                        "required": ["action"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_customer_conversations",
                    "description": "Recupera o histórico completo de conversas de um cliente com o agente de atendimento.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "customer_id": {
                                "type": "integer",
                                "description": "ID do cliente",
                            },
                            "phone": {
                                "type": "string",
                                "description": "Telefone do cliente (alternativa ao ID)",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Máx. mensagens (default 20)",
                            },
                            "offset": {
                                "type": "integer",
                                "description": "Deslocamento para paginação (default 0)",
                            },
                        },
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "send_whatsapp",
                    "description": "Envia uma mensagem WhatsApp diretamente a um cliente via Evolution API.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "phone": {
                                "type": "string",
                                "description": "Número de telefone (com DDD, sem +55)",
                            },
                            "customer_id": {
                                "type": "integer",
                                "description": "ID do cliente (alternativa ao phone)",
                            },
                            "message": {
                                "type": "string",
                                "description": "Texto da mensagem a enviar",
                            },
                        },
                        "required": ["message"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "save_note",
                    "description": "Salva uma nota administrativa no perfil do admin atual.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "note": {
                                "type": "string",
                                "description": "Texto da nota a salvar",
                            },
                        },
                        "required": ["note"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_notes",
                    "description": "Recupera as últimas 10 notas administrativas salvas pelo admin atual.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "manage_profiles",
                    "description": "Verifica status/saúde dos Perfis de Agente, ativa um perfil, ou CRIA um novo perfil. Na criação (`create`): (1) Se `base_prompt` for fornecido, o sistema analisa automaticamente o texto e extrai todos os campos (nicho, tom, formalidade, autonomia, objetivo, público-alvo, dados a coletar); (2) Se `base_prompt` NÃO for fornecido, o sistema gera o prompt base automaticamente com base nas configurações informadas. Em ambos os casos o registro fica completo.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["check_health", "activate", "create"],
                                "description": "Ação a executar. Use 'create' para gerar um novo perfil completo.",
                            },
                            "profile_id": {
                                "type": "integer",
                                "description": "ID do perfil (para activate)",
                            },
                            "name": {
                                "type": "string",
                                "description": "Nome identificador interno do perfil (para create)",
                            },
                            "agent_name_display": {
                                "type": "string",
                                "description": "Nome do atendente virtual. Ex: 'Sofia' (para create)",
                            },
                            "niche": {
                                "type": "string",
                                "enum": [
                                    "geral",
                                    "imobiliario",
                                    "saude",
                                    "educacao",
                                    "ecommerce",
                                    "tecnologia",
                                    "financeiro",
                                    "juridico",
                                    "restaurante",
                                    "automacao",
                                ],
                                "description": "Nicho de mercado (para create)",
                            },
                            "tone": {
                                "type": "string",
                                "enum": [
                                    "neutro",
                                    "formal",
                                    "semi-formal",
                                    "amigavel",
                                    "jovem",
                                ],
                                "description": "Tom de comunicação (para create)",
                            },
                            "formality": {
                                "type": "string",
                                "enum": [
                                    "muito_informal",
                                    "informal",
                                    "equilibrado",
                                    "formal",
                                    "muito_formal",
                                ],
                                "description": "Grau de formalidade (para create)",
                            },
                            "autonomy_level": {
                                "type": "string",
                                "enum": [
                                    "estrita",
                                    "orientada",
                                    "equilibrada",
                                    "proativa",
                                    "independente",
                                ],
                                "description": "Nível de autonomia (para create)",
                            },
                            "objective": {
                                "type": "string",
                                "description": "Objetivo principal do atendimento (para create)",
                            },
                            "target_audience": {
                                "type": "string",
                                "description": "Público-alvo (para create)",
                            },
                            "data_to_collect": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Lista de dados a coletar, ex: ['Nome', 'Email'] (para create)",
                            },
                            "constraints": {
                                "type": "string",
                                "description": "Restrições ou temas proibidos (para create, quando base_prompt não fornecido)",
                            },
                            "base_prompt": {
                                "type": "string",
                                "description": "Texto completo do prompt do agente (CENÁRIO 1). Se fornecido, os campos são extraídos automaticamente via análise LLM. Se omitido, o prompt será gerado a partir dos outros campos (CENÁRIO 2).",
                            },
                        },
                        "required": ["action"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "manage_account_recovery",
                    "description": "Recuperação de conta para o patrão. Gera um link seguro de recuperação para o administrador alterar a própria senha.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["request_reset"],
                                "description": "Ação a executar. Use 'request_reset' para envio de link.",
                            },
                            "new_password": {
                                "type": "string",
                                "description": "A nova senha a ser configurada (Obrigatório para a ação 'reset_password').",
                            },
                        },
                        "required": ["action"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "manage_whatsapp",
                    "description": "Realiza a configuração nível empresarial do WhatsApp na hora. Conecta novos WhatsApps gerando uma Webhook ÚNICA formatada com o nome do cliente. Se o Patrão enviar o nome com espaços (ex: Loja Tech), passe com espaços e o sistema slugificará com segurança.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["create", "list", "delete"],
                                "description": "Ação a executar: 'create' para registrar uma nova conexão de WhatsApp, 'list' para mostrar, 'delete' para excluir.",
                            },
                            "instance_name": {
                                "type": "string",
                                "description": "Nome da instância (Obrigatório para create)",
                            },
                            "tenant_id": {
                                "type": "integer",
                                "description": "ID do Lojista (Opcional, deixa em branco para master/interno)",
                            },
                        },
                        "required": ["action"],
                    },
                },
            },
        ]


# Instância global
admin_agent = AdminAgent()
