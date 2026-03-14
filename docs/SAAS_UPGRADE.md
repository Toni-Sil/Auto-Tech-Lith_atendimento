# SaaS Upgrade — Documentação Técnica

## Novos Módulos — Branch `feature/saas-upgrade`

### 1. Tenant Context Middleware
**Arquivo:** `src/middleware/tenant_context.py`

Isola automática de tenants em todas as requisições:
- Extrai `tenant_id` do JWT ou do header `X-Tenant-ID`
- Injeta em `request.state.tenant_id`
- Dependency `get_current_tenant_id(request)` para usar em rotas

**Como usar em uma rota:**
```python
from src.middleware.tenant_context import get_current_tenant_id

@router.get("/tickets")
async def list_tickets(tenant_id: int = Depends(get_current_tenant_id)):
    # Aqui tenant_id é garantido e validado
    ...
```

**Registrar no main.py:**
```python
from src.middleware.tenant_context import TenantContextMiddleware
app.add_middleware(TenantContextMiddleware)
```

---

### 2. Handoff Service (Escalação Humana)
**Arquivo:** `src/services/handoff_service.py`  
**API:** `src/api/handoff.py`

Gerencia o ciclo AI ↔ Humano:

```
IA com baixa confiança
        ↓
handoff_service.request_handoff()  ← pausa IA + notifica operador
        ↓
Operador acessa painel → POST /api/v1/handoff/take/{conv_id}
        ↓
Operador resolve → POST /api/v1/handoff/release/{conv_id}
        ↓
IA retoma automaticamente
```

**Motivos de handoff:**
- `low_confidence` — IA com baixa confiança
- `customer_request` — Cliente pediu humano
- `critical_issue` — Problema crítico
- `repeated_failure` — IA falhou 3x
- `operator_override` — Override manual

**Registrar no main.py:**
```python
from src.api.handoff import handoff_router
app.include_router(handoff_router, prefix=f"{settings.API_V1_STR}/handoff", tags=["handoff"])
```

---

### 3. Knowledge Base Service (RAG)
**Arquivo:** `src/services/knowledge_service.py`  
**API:** `src/api/knowledge.py`

Base de conhecimento por tenant com busca vetorial:

```
Upload texto → Chunking → Embedding (OpenAI) → Índice em memória

Pergunta do cliente → Embed → Cosine similarity → Top-5 chunks
                                                         ↓
                                              Injeta no prompt do LLM
```

**Endpoints:**
- `POST /api/v1/knowledge/ingest` — Upload de documento
- `GET /api/v1/knowledge/docs` — Listar documentos indexados
- `DELETE /api/v1/knowledge/{doc_id}` — Remover documento
- `POST /api/v1/knowledge/query` — Testar busca
- `GET /api/v1/knowledge/stats` — Estatísticas do índice

**Como usar no customer_service_agent:**
```python
from src.services.knowledge_service import knowledge_service

# Antes de chamar o LLM:
context = await knowledge_service.build_context_prompt(
    tenant_id=tenant_id,
    question=user_message
)
system_prompt = base_prompt + "\n\n" + context
```

**Registrar no main.py:**
```python
from src.api.knowledge import knowledge_router
app.include_router(knowledge_router, prefix=f"{settings.API_V1_STR}/knowledge", tags=["knowledge"])
```

---

### 4. Billing Service (Stripe)
**Arquivo:** `src/services/billing_service.py`  
**API:** `src/api/billing_stripe.py`

Integração completa com Stripe:

**Variáveis de ambiente necessárias (.env):**
```env
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_BASIC=price_...
STRIPE_PRICE_PRO=price_...
STRIPE_PRICE_ENTERPRISE=price_...
```

**Planos e limites:**
| Plano | Mensagens/mês | Mensagens/dia | Agentes | WhatsApp |
|---|---|---|---|---|
| basic | 1.000 | 100 | 1 | 1 |
| pro | 10.000 | 500 | 3 | 3 |
| enterprise | 100.000 | 5.000 | 10 | 10 |

**Registrar no main.py:**
```python
from src.api.billing_stripe import billing_stripe_router
app.include_router(billing_stripe_router, prefix=f"{settings.API_V1_STR}/billing/stripe", tags=["billing-stripe"])
```

---

### 5. Stuck Ticket Scanner (Butler proativo)
**Arquivo:** `src/agents/butler/stuck_ticket_scanner.py`  
**Integrado ao:** `src/workers/butler_worker.py`

Roda a cada 15 minutos. Detecta tickets abertos sem resposta e notifica o operador via Telegram antes que o cliente fique frustrado.

**Limiares por plano:**
| Plano | Alerta após |
|---|---|
| basic | 2 horas |
| pro | 1 hora |
| enterprise | 30 minutos |

---

## Checklist de Integração no main.py

```python
# 1. Adicionar middleware (antes dos outros middlewares)
from src.middleware.tenant_context import TenantContextMiddleware
app.add_middleware(TenantContextMiddleware)

# 2. Registrar rotas
from src.api.handoff import handoff_router
from src.api.knowledge import knowledge_router
from src.api.billing_stripe import billing_stripe_router

app.include_router(handoff_router, prefix=f"{settings.API_V1_STR}/handoff", tags=["handoff"])
app.include_router(knowledge_router, prefix=f"{settings.API_V1_STR}/knowledge", tags=["knowledge"])
app.include_router(billing_stripe_router, prefix=f"{settings.API_V1_STR}/billing/stripe", tags=["billing-stripe"])

# 3. Adicionar ao .env
# STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_PRICE_BASIC/PRO/ENTERPRISE
```

## Próximos Passos Recomendados

1. **Revisar e fazer merge** desta branch para `main` após testes
2. **Adicionar pgvector** ao PostgreSQL para persistência do índice de knowledge (atualmente in-memory)
3. **Migrar frontend** para React/TypeScript com inbox unificado
4. **Templates de nicho** (auto-elétrica, clínica, salão) para onboarding acelerado
5. **Configurar Stripe** com os 3 planos e webhook no dashboard Stripe
