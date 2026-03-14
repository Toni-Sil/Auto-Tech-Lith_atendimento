# Sprint 1 — Checklist de Implementação

## Status Geral
- [ ] Branch `sprint-1/saas-foundation` criada
- [ ] PR aberto para review
- [ ] Testes passando
- [ ] Deploy em staging

---

## Bloco 1 — Multi-Tenant Seguro

### Middleware
- [ ] `src/middleware/tenant_context.py` implementado
- [ ] Registrado no `src/main.py` como middleware FastAPI
- [ ] Rotas públicas configuradas em `PUBLIC_PATHS`
- [ ] Testado com request sem token (deve retornar 401)
- [ ] Testado com token de tenant A acessando dados do tenant B (deve ser bloqueado)

### Base Model
- [ ] `src/models/base_tenant.py` criado
- [ ] Models de negócio migrando para `BaseTenantModel` (tickets, leads, conversations, customers)
- [ ] Index composto `tenant_id` aplicado

### RLS no PostgreSQL
- [ ] `migrations/rls_setup.sql` executado no banco
- [ ] Query de verificação retorna `rowsecurity = true` para todas as tabelas
- [ ] Testado: query sem `SET LOCAL app.current_tenant` retorna 0 linhas (não vaza)
- [ ] Testado: query com tenant_id correto retorna apenas dados daquele tenant

---

## Bloco 2 — Butler Scheduler

- [ ] `src/workers/butler_scheduler.py` implementado
- [ ] `apscheduler` adicionado ao `requirements.txt`
- [ ] `register_all_jobs()` chamado no `startup` do FastAPI
- [ ] `scheduler.start()` chamado no `startup`
- [ ] `scheduler.shutdown()` chamado no `shutdown`
- [ ] Job `check_stuck_tickets` testado manualmente
- [ ] Job `check_quota_health` testado manualmente
- [ ] Job `send_daily_digest` testado com tenant ativo
- [ ] Logs aparecendo corretamente no `butler_logs`

### Integrar no main.py
```python
# src/main.py — adicionar no startup:
from src.workers.butler_scheduler import scheduler, register_all_jobs

@app.on_event("startup")
async def startup():
    register_all_jobs()
    scheduler.start()

@app.on_event("shutdown")
async def shutdown():
    scheduler.shutdown(wait=False)
```

---

## Bloco 3 — Onboarding API

- [ ] `src/api/onboarding.py` implementado
- [ ] Router registrado no `src/main.py`
- [ ] Passo 1 `/register` testado — cria tenant + admin + retorna JWT
- [ ] Passo 2 `/connect` integrado com `whatsapp_service.py`
- [ ] Passo 3 `/configure` testado — cria AgentProfile + ativa tenant
- [ ] Fluxo completo testado em sequência
- [ ] `get_current_tenant_id` substituindo `lambda: None` nos endpoints

---

## Bloco 4 — Dependências

Adicionar ao `requirements.txt`:
```
apscheduler>=3.10.0
bcrypt>=4.0.0
PyJWT>=2.8.0
```

---

## Testes Mínimos Necessários

```bash
# 1. Testar isolamento de tenant
curl -H "Authorization: Bearer <token_tenant_1>" /api/tickets
# Deve retornar APENAS tickets do tenant 1

# 2. Testar onboarding
curl -X POST /api/onboarding/register \
  -d '{"business_name": "Minha Oficina", "email": "dono@oficina.com", "password": "senha123", "phone": "5511999999999", "niche": "auto_eletrica"}'
# Deve retornar tenant_id + token + step=1

# 3. Testar butler manualmente
python -c "import asyncio; from src.workers.butler_scheduler import check_stuck_tickets; asyncio.run(check_stuck_tickets())"
# Deve rodar sem erro e logar no butler_logs
```

---

## Próximo Sprint (Sprint 2)
- Editor visual de personalidade do agente
- Handoff humano nativo
- Base de conhecimento por tenant (RAG)
- Dashboard React/TypeScript
- Billing com Stripe
