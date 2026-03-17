# Auto Tech Lith — Architecture Overview

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENTS                                   │
│  Browser Dashboard   WhatsApp (Evolution API)   Telegram Bot    │
└──────────────┬──────────────────┬───────────────────────────────┘
               │                  │
               ▼                  ▼
┌──────────────────────────────────────────────────────────────── │
│              FASTAPI APPLICATION (src/)                         │
│                                                                  │
│  ┌─────────┐  ┌──────────┐  ┌───────────┐  ┌────────────────┐  │
│  │  Auth   │  │  Tenant  │  │  Webhooks │  │   Billing      │  │
│  │  + MFA  │  │  + Quota │  │ (WA+TG)   │  │  (Stripe)      │  │
│  └─────────┘  └──────────┘  └───────────┘  └────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              AI AGENT LAYER (src/agents/)                │   │
│  │  CustomerServiceAgent → LLMService (OpenAI)              │   │
│  │  Tools: schedule_meeting, update_customer_info,          │   │
│  │         check_availability                               │   │
│  │  Cache: Redis async pool (singleton)                     │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              BUTLER AGENT (src/workers/)                 │   │
│  │  APScheduler — 8 background jobs                        │   │
│  │  Lead nurturing, follow-up, cleanup, metrics             │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────────┘
                             │
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
   ┌─────────────┐   ┌──────────────┐   ┌────────────┐
   │ PostgreSQL  │   │    Redis     │   │  Evolution │
   │  (Primary)  │   │  (Cache+Q)   │   │    API     │
   └─────────────┘   └──────────────┘   └────────────┘
```

## Multi-Tenant Model

Each tenant is isolated by `tenant_id` on every model.
`TenantContextMiddleware` blocks requests for unregistered instances.

## Security Layers

1. JWT Auth + MFA (TOTP)
2. Rate Limiting (per-IP)
3. CSP with per-request nonces
4. HSTS, X-Frame-Options, X-Content-Type-Options
5. Encryption key vault (Fernet) for AI API keys
6. Role-based permissions

## CI/CD Pipeline

```
Push → GitHub Actions CI
  ├── Backend tests (pytest + PostgreSQL + Redis services)
  ├── Frontend build (Tailwind CSS compilation)
  └── Security scan (Bandit SAST + Safety)

Merge to main → Deploy workflow
  └── SSH to VPS → git pull → docker compose up → alembic upgrade head
```

## Frontend Structure

```
frontend/
├── css/
│   ├── src/input.css    ← Tailwind source (design tokens + components)
│   └── tailwind.min.css ← Compiled output (not committed, built by CI)
├── js/
│   ├── api.js           ← Centralized fetch client (auth, refresh, errors)
│   ├── theme.js         ← Dark/light mode manager
│   ├── toast.js         ← Notification system
│   ├── sidebar.js       ← Collapsible sidebar
│   ├── main.js          ← Admin dashboard logic
│   ├── master.js        ← Master admin logic
│   └── profiles_webhooks.js
├── index.html           ← Admin dashboard
├── master.html          ← Master admin portal
├── client.html          ← Client portal
├── login.html
└── home.html            ← Landing page
```
