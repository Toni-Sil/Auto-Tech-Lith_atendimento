# Integrações necessárias no `src/main.py`

Este documento detalha exatamente o que adicionar no `main.py` para ativar
todos os recursos do Sprint 1 e Sprint 2.

---

## 1. Tenant Context Middleware

Adicionar ANTES dos outros middlewares (linha ~17, após os imports):

```python
from src.middleware.tenant_context import TenantContextMiddleware

# Adicionar como primeiro middleware (aplica a todos os requests)
app.add_middleware(TenantContextMiddleware)
```

**Ordem correta dos middlewares (de cima para baixo):**
```python
app.add_middleware(TenantContextMiddleware)   # 1. Tenant context (novo)
app.add_middleware(PrometheusMetricsMiddleware)  # 2. Métricas
app.add_middleware(RateLimitMiddleware)          # 3. Rate limit
# ... CORSMiddleware (já existente)
```

---

## 2. Onboarding Router

Adicionar junto aos outros routers:

```python
from src.api.onboarding import router as onboarding_router
app.include_router(onboarding_router)  # sem prefix extra, já tem /api/onboarding
```

---

## 3. Agent Profile Editor Router

```python
from src.api.agent_profile_editor import router as agent_profile_router
app.include_router(agent_profile_router)  # já tem prefix /api/v1/agent
```

---

## 4. Registrar modelo base_tenant no startup

No `startup_event()`, adicionar junto aos outros imports de models:

```python
import src.models.base_tenant  # BaseTenantModel
```

---

## 5. Atualizar log do startup

No final do `startup_event()`, atualizar a mensagem:

```python
logger.info("Startup: Butler Agent scheduler started with 8 background jobs.")  # era 5
```

---

## Resultado final — novos endpoints ativos

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| POST | `/api/onboarding/register` | Passo 1: criar conta + tenant |
| POST | `/api/onboarding/connect` | Passo 2: conectar WhatsApp |
| POST | `/api/onboarding/configure` | Passo 3: configurar agente |
| GET | `/api/v1/agent/profile` | Ver perfil do agente |
| PUT | `/api/v1/agent/profile` | Editar personalidade |
| POST | `/api/v1/agent/profile/preview` | Testar agente |
| POST | `/api/v1/agent/profile/activate` | Publicar agente |
| GET | `/api/v1/agent/profile/templates` | Templates por nicho |
| POST | `/api/v1/agent/profile/apply-template/{niche}` | Aplicar template |

---

## Jobs do Butler agora ativos (8 total)

| Job | Frequência | O que faz |
|-----|-----------|----------|
| `infra_health_check` | 30min | Saúde da infra |
| `quota_patrol` | 60min | Quotas por tenant |
| `churn_scan` | diário 08h | Risco de churn |
| `daily_report` | diário 07h | Relatório master |
| `log_rotation` | diário 03h | Limpeza de logs |
| `stuck_tickets_scan` | **15min** | Tickets travados *(novo)* |
| `hot_leads_scan` | **1h** | Leads quentes esquecidos *(novo)* |
| `webhook_health` | **10min** | Webhooks com falha *(novo)* |
