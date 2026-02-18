import json
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy import select, func, desc, or_

from src.agents.base_agent import BaseAgent
from src.services.llm_service import llm_service
from src.models.database import async_session
from src.models.customer import Customer
from src.models.meeting import Meeting, MeetingStatus
from src.models.ticket import Ticket, TicketStatus, TicketPriority
from src.models.admin import AdminUser
from src.utils.logger import setup_logger
from src.services.permission_service import PermissionService, Role, PermissionResult

logger = setup_logger(__name__)

class AdminAgent(BaseAgent):
    """
    Refactored Admin Agent: Planner -> Policy -> Executor.
    Uses PermissionService for RBAC.
    """
    
    def __init__(self):
        super().__init__()
        self.auth_attempts = {}
        self.system_prompt_template = """
        # Sistema: Admin Agent (Auto Tech Lith) - Architect Mode
        
        ## 1. IDENTIDADE E CONTROLE
        Você é o **Orquestrador Administrativo** do sistema.
        - **Usuário Atual:** {user_identity}
        - **Role/Permissão:** {user_role}
        - **Data/Hora:** {current_time}
        
        ## 2. FLUXO DE ORQUESTRAÇÃO (Planner -> Policy -> Executor)
        Ao receber um comando:
        1. **Entenda a intenção**: O que o usuário quer alterar ou consultar?
        2. **Gere um Plano**: Decida quais ferramentas chamar.
        3. **Verifique Permissões**: Você sabe que certas ações (como DELETAR) exigem permissão alta.
        4. **Execute**: Chame a ferramenta `create_plan` ou a ferramenta específica diretamente.
        
        ## 3. REGRAS CRÍTICAS
        - **Segurança**: Nunca execute ações destrutivas (delete/cancel) sem certeza absoluta.
        - **Feedback**: Se a ferramenta retornar erro, explique ao usuário.
        - **Confirmação**: Se o usuário confirmar uma ação pendente (dizendo "Confirmar"), prossiga.
        
        ## 4. FORMATO DE PLANO
        Para ações complexas ou múltiplas, chame a ferramenta `create_plan`. 
        Para ações simples (ex: "Buscar cliente"), chame a ferramenta `manage_customers` diretamente.
        """

    async def get_system_prompt(self, context: Dict[str, Any]) -> str:
        return self.system_prompt_template

    async def identify_user(self, user_id: int, username: str, message: str) -> str:
        """
        Manages identification. Returns auth status string.
        """
        async with async_session() as session:
            # 1. Check by Telegram ID
            result = await session.execute(select(AdminUser).where(AdminUser.telegram_id == user_id))
            admin = result.scalar_one_or_none()
            
            if admin:
                admin.last_active_at = datetime.now()
                # Update username if changed
                if username and username != "Unknown" and admin.username != username:
                     if f"({username})" not in admin.name:
                         admin.name = f"{admin.name} ({username})"
                await session.commit()
                return f"AUTHORIZED:{admin.name}:{admin.role}"
            
            # 2. Check by Access Code (Legacy/First access)
            # Fetch all to check code
            result = await session.execute(select(AdminUser))
            all_admins = result.scalars().all()
            
            for adm in all_admins:
                if adm.access_code and adm.access_code == message.strip():
                     adm.telegram_id = user_id
                     adm.last_active_at = datetime.now()
                     adm.username = username
                     await session.commit()
                     return f"SUCCESS:{adm.name}:{adm.role}"
                     
            return "UNKNOWN"

    async def process_message(self, message: str, context: Dict[str, Any]) -> str:
        user_id = context.get("user_id")
        username = context.get("username", "Admin")
        
        # 1. Auth & Role
        auth_status = await self.identify_user(user_id, username, message)
        
        user_identity = "Visitante"
        user_role_str = "viewer"
        role_enum = Role.VIEWER
        
        if auth_status.startswith("AUTHORIZED") or auth_status.startswith("SUCCESS"):
            parts = auth_status.split(":")
            user_identity = parts[1]
            user_role_str = parts[2] if len(parts) > 2 else "admin"
            role_enum = PermissionService.get_role_from_string(user_role_str)
        elif auth_status == "UNKNOWN":
            if "acesso" in message.lower() or "código" in message.lower():
                return "Por favor, digite seu código de acesso para vincular este Telegram."
            # Allow limited interaction or generic response
            # But let's restrict strict actions.
            pass

        # 2. Prepare Prompt
        current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        prompt = self.system_prompt_template.format(
            user_identity=user_identity, 
            current_time=current_time_str,
            user_role=user_role_str.upper()
        )
        
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": message}
        ]
        
        tools = self._get_tools_schema()
        
        # 3. LLM Call
        response_msg = await llm_service.get_chat_response(messages, tools=tools)
        
        # 4. Handle Tool Calls (The "Planner" Output)
        if response_msg.tool_calls:
            tool_calls = response_msg.tool_calls
            results = []
            
            for tc in tool_calls:
                func_name = tc.function.name
                args = json.loads(tc.function.arguments)
                
                # Expand "create_plan" into individual steps if used
                steps_to_execute = []
                if func_name == "create_plan":
                    steps_to_execute = args.get("steps", [])
                else:
                    # Treat direct call as single step
                    steps_to_execute = [{"tool": func_name, "args": args, "action": args.get("action", "")}]
                
                # Execute Plan Loop
                for step in steps_to_execute:
                    step_tool = step.get("tool") or step.get("tool_name")
                    step_args = step.get("args") or step.get("arguments") or {}
                    step_action = step.get("action") or step_args.get("action")
                    
                    # A. Permission Check
                    perm_result = PermissionService.check_permission(role_enum, step_tool, step_action)
                    
                    if perm_result == PermissionResult.DENIED:
                        results.append(f"❌ Ação negada: {step_tool}.{step_action} (Role: {user_role_str})")
                        continue
                        
                    if perm_result == PermissionResult.NEEDS_CONFIRMATION:
                        # Stateless confirmation check
                        if "confirmar" not in message.lower() and "sim" not in message.lower():
                            results.append(f"⚠️ Ação requer confirmação: {step_tool}.{step_action}. Responda 'CONFIRMAR' para prosseguir.")
                            continue
                            
                    # B. Execution
                    try:
                        # Ensure action is passed to the method
                        final_args = step_args.copy()
                        if "action" not in final_args and step_action:
                            final_args["action"] = step_action
                            
                        res = await self._execute_tool(step_tool, final_args)
                        results.append(f"✅ {step_tool}: {res}")
                    except Exception as e:
                        logger.error(f"Error executing {step_tool}: {e}")
                        results.append(f"❌ Erro em {step_tool}: {str(e)}")
            
            # 5. Final LLM Response based on results
            messages.append(response_msg)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_calls[0].id, 
                "content": "\n".join(results)
            })
            
            final_response = await llm_service.get_chat_response(messages)
            return final_response.content
            
        return response_msg.content or "Entendido."

    async def _execute_tool(self, tool_name: str, args: Dict[str, Any]) -> str:
        """Dispatcher for tools."""
        if tool_name == "manage_customers":
            return await self.manage_customers(**args)
        elif tool_name == "manage_tickets":
            return await self.manage_tickets(**args)
        elif tool_name == "manage_meetings":
            return await self.manage_meetings(**args)
        elif tool_name == "manage_admins":
            return await self.manage_admins(**args)
        elif tool_name == "get_daily_summary":
            return await self.get_daily_summary()
        elif tool_name == "save_note":
             pass
        elif tool_name == "get_notes":
             pass
             
        return f"Ferramenta {tool_name} não implementada ou não mapeada."

    # --- Tool Implementations (Copied/Adapted) ---
    
    async def get_daily_summary(self) -> str:
        today = date.today()
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        async with async_session() as session:
             new_leads = await session.scalar(select(func.count(Customer.id)).where(Customer.created_at >= today_start))
             open_tickets = await session.scalar(select(func.count(Ticket.id)).where(Ticket.status == TicketStatus.OPEN))
             meetings_today = await session.scalar(select(func.count(Meeting.id)).where(Meeting.date == today))
        return f"📅 Resumo ({today.strftime('%d/%m')}):\nLeads: {new_leads}\nTickets: {open_tickets}\nReuniões: {meetings_today}"

    async def manage_customers(self, action: str, query: Optional[str] = None, customer_id: Optional[int] = None, data: Optional[str] = None) -> str:
        async with async_session() as session:
            if action == "search":
                if not query: return "Query necessária."
                result = await session.execute(select(Customer).where(or_(Customer.name.ilike(f"%{query}%"), Customer.phone.ilike(f"%{query}%"))).limit(5))
                customers = result.scalars().all()
                if not customers: return "Nenhum cliente encontrado."
                return "\n".join([f"🆔 {c.id} | {c.name} | {c.phone}" for c in customers])
            elif action == "create":
                if not data: return "Dados JSON necessários."
                try: d = json.loads(data.replace("'", '"'))
                except: return "JSON inválido."
                new_c = Customer(**d)
                session.add(new_c)
                await session.commit()
                return f"Cliente {new_c.name} (ID {new_c.id}) criado."
            elif action == "update":
                if not customer_id or not data: return "ID e dados necessários."
                c = await session.get(Customer, customer_id)
                if not c: return "Cliente não encontrado."
                try: d = json.loads(data.replace("'", '"'))
                except: return "JSON inválido."
                for k,v in d.items(): setattr(c, k, v)
                await session.commit()
                return "Cliente atualizado."
            elif action == "delete":
                if not customer_id: return "ID necessário."
                c = await session.get(Customer, customer_id)
                if not c: return "Cliente não encontrado."
                await session.delete(c)
                await session.commit()
                return f"Cliente {c.name} deletado."
        return "Ação inválida."

    async def manage_tickets(self, action: str, status: Optional[str]=None, priority: Optional[str]=None, customer_id: Optional[int]=None, ticket_id: Optional[int]=None, subject: Optional[str]=None) -> str:
        async with async_session() as session:
            if action == "list":
                stmt = select(Ticket).order_by(desc(Ticket.created_at)).limit(5)
                res = await session.execute(stmt)
                return "\n".join([f"#{t.id} {t.subject} ({t.status})" for t in res.scalars()])
            elif action == "create":
                 if not customer_id or not subject: return "ID e assunto necessários."
                 t = Ticket(customer_id=customer_id, subject=subject, status=TicketStatus.OPEN, priority=priority or TicketPriority.MEDIUM)
                 session.add(t)
                 await session.commit()
                 return f"Ticket #{t.id} criado."
            elif action == "update":
                if not ticket_id: return "ID necessário."
                t = await session.get(Ticket, ticket_id)
                if not t: return "Ticket não encontrado."
                if status: t.status = status
                if priority: t.priority = priority
                await session.commit()
                return f"Ticket #{t.id} atualizado."
        return "Ação inválida."

    async def manage_meetings(self, action: str, customer_id: Optional[int]=None, date_str: Optional[str]=None, time_str: Optional[str]=None, meeting_id: Optional[int]=None, days: int=7) -> str:
        async with async_session() as session:
            if action == "list":
                 limit = date.today() + timedelta(days=days)
                 res = await session.execute(select(Meeting).where(Meeting.date <= limit))
                 return "\n".join([f"{m.date} {m.time} | ID {m.id} | {m.status}" for m in res.scalars()])
            elif action == "schedule":
                 if not customer_id or not date_str or not time_str: return "ID, Data e Hora necessários."
                 try:
                     d = datetime.strptime(date_str, "%Y-%m-%d").date()
                     t = datetime.strptime(time_str, "%H:%M").time()
                     m = Meeting(customer_id=customer_id, date=d, time=t, status=MeetingStatus.SCHEDULED)
                     session.add(m)
                     await session.commit()
                     return f"Reunião agendada: {d} {t}"
                 except Exception as e: return f"Erro: {e}"
            elif action == "cancel":
                 if not meeting_id: return "ID necessário."
                 m = await session.get(Meeting, meeting_id)
                 if m:
                     m.status = MeetingStatus.CANCELLED
                     await session.commit()
                     return "Reunião cancelada."
                 return "Reunião não encontrada."
        return "Ação inválida."

    async def manage_admins(self, action: str, name: Optional[str]=None, username: Optional[str]=None, admin_id: Optional[int]=None) -> str:
        async with async_session() as session:
            if action == "list":
                 res = await session.execute(select(AdminUser))
                 return "\n".join([f"#{a.id} {a.name} ({a.role})" for a in res.scalars()])
            elif action == "delete":
                 if not admin_id: return "ID necessário."
                 a = await session.get(AdminUser, admin_id)
                 if a:
                     await session.delete(a)
                     await session.commit()
                     return f"Admin {a.name} removido."
                 return "Admin não encontrado."
            # create implementation skipped for brevity but should exist
        return "Ação não implementada no refactor rápido."

    def _get_tools_schema(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "create_plan",
                    "description": "Cria um plano de execução.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "steps": {
                                "type": "array", 
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "tool": {"type": "string"},
                                        "action": {"type": "string"},
                                        "args": {"type": "object"}
                                    },
                                    "required": ["tool", "action", "args"]
                                }
                            }
                        },
                        "required": ["steps"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                     "name": "manage_customers",
                     "description": "Gerencia clientes.",
                     "parameters": {
                         "type": "object",
                         "properties": {
                             "action": {"type": "string", "enum": ["search", "create", "update", "delete"]},
                             "query": {"type": "string"},
                             "customer_id": {"type": "integer"},
                             "data": {"type": "string"}
                         },
                         "required": ["action"]
                     }
                }
            },
            {
                "type": "function", 
                "function": {
                    "name": "manage_tickets",
                    "description": "Gerencia tickets.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": ["list", "create", "update"]},
                            "status": {"type": "string"},
                            "priority": {"type": "string"},
                            "customer_id": {"type": "integer"},
                            "ticket_id": {"type": "integer"},
                            "subject": {"type": "string"}
                        },
                        "required": ["action"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "manage_meetings",
                    "description": "Gerencia reuniões.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": ["list", "schedule", "cancel"]},
                            "days": {"type": "integer"},
                            "customer_id": {"type": "integer"},
                            "date": {"type": "string"},
                            "time": {"type": "string"},
                            "meeting_id": {"type": "integer"}
                        },
                        "required": ["action"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "manage_admins",
                    "description": "Gerencia admins.",
                    "parameters": {
                         "type": "object",
                         "properties": {
                             "action": {"type": "string", "enum": ["list", "delete"]},
                             "admin_id": {"type": "integer"}
                         },
                         "required": ["action"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_daily_summary",
                    "description": "Resumo do dia.",
                    "parameters": {"type": "object", "properties": {}, "required": []}
                }
            }
        ]

admin_agent = AdminAgent()
