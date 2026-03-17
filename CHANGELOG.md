# Changelog

All notable changes to **Auto Tech Lith** are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased] — feat/market-ready-improvements

### Added
- **CI/CD** — GitHub Actions pipeline: pytest (PostgreSQL + Redis), Tailwind build, Bandit SAST, Safety audit
- **Auto-deploy** — `.github/workflows/deploy.yml` via SSH ao merge em `main`
- **Design System** — Tailwind compilado localmente (elimina CDN em produção)
  - Design tokens CSS (light + dark mode) via CSS custom properties
  - Componentes: `.card`, `.metric-card`, `.btn-*`, `.badge-*`, `.input`, `.sidebar`, `.topbar`, `.data-table`, `.toast`, `.skeleton`, `.modal`
- **JS Modules** — `theme.js`, `toast.js`, `api.js` (JWT auto-refresh), `sidebar.js`
- **`/health` detalhado** — check de dependências (PostgreSQL, Redis, Evolution API) com latência
- **`/status`** — Página pública de status com dark mode e refresh automático (30s)
- **`/robots.txt`** — Gerado dinamicamente com `PUBLIC_URL`
- **`/sitemap.xml`** — Sitemap XML para SEO da landing page
- **`PerformanceMiddleware`** — Header `Server-Timing` + log de requests lentos (>500ms)
- **`RequestIDMiddleware`** — Header `X-Request-ID` para distributed tracing
- **`tests/`** — Estrutura de testes organizada com conftest async, test_health, test_auth
- **`docs/ARCHITECTURE.md`** — Diagrama ASCII completo da arquitetura
- **`docs/DEPLOYMENT.md`** — Guia de primeiro deploy e deploy contínuo

### Fixed
- **`favicon.ico`** — Retorna 204 em vez de HTML quando não existe (evita erro 400 no browser)
- **CSP** — Removido `cdn.tailwindcss.com` do `script-src` (Tailwind agora é local)
- **`.gitignore`** — `backups/`, `frontend/dist/`, `requirements_additions.txt` ignorados
- **`pytest.ini`** — `asyncio_mode = auto`, `testpaths = tests`

### Changed
- Middleware stack reordenada: `RequestID` → `Performance` → `Tenant` → `Prometheus` → `RateLimit`
- `.env.example` atualizado com `REDIS_HOST`, `REDIS_PORT`, `STRIPE_*`, documentação de CI/CD secrets

---

## [Unreleased] — fix/csp-nonce-and-alembic

### Added
- **CSP nonce** — Nonce por request injetado em `<script>` e `<style>` tags via regex
- **Alembic no startup** — `alembic upgrade head` executado no lifespan (substitui `create_all` em produção)
- **`alembic.ini`** + `migrations/` configurados
- **`psycopg2-binary`** e **`alembic`** adicionados ao `requirements.txt`
- **`src/schemas/preferences.py`** movido para local correto; shim de retrocompatibilidade em `schemas_preferences.py`
- **Redis async pool singleton** — `redis.asyncio` com pool global, fechado no shutdown
- **`lifespan` context manager** — substitui `@app.on_event("startup")` deprecado

---

## [1.0.0] — 2026-01-01 (baseline)

### Added
- Multi-tenant SaaS com FastAPI + PostgreSQL + Redis
- Agente de atendimento AI (OpenAI) via WhatsApp (Evolution API) e Telegram
- Autenticação JWT + MFA TOTP
- Butler Agent com APScheduler (8 jobs)
- Billing Stripe + quotas por tenant
- Dashboard admin, portal master, portal cliente
- LGPD compliance (termos, privacidade, consentimento)
