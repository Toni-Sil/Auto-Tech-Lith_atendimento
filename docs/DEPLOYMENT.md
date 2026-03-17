# Deployment Guide

## Stack de Hospedagem

| Componente | Tecnologia |
|---|---|
| VPS | Hostinger KVM |
| Orquestrador | Dokploy |
| Reverse Proxy / SSL | Traefik (gerenciado pelo Dokploy) |
| CI | GitHub Actions (testes + build) |
| CD | Dokploy (Git webhook no branch `main`) |

---

## Como o Deploy Funciona

O Dokploy monitora o branch `main` via **Git webhook**.
Qualquer push para `main` dispara automaticamente:

```
git push main
  └── GitHub Actions CI (testes + build check)
  └── Dokploy recebe webhook
        └── git pull
        └── docker compose build (multi-stage: Node build + Python runtime)
        └── docker compose up -d --remove-orphans
        └── alembic upgrade head (via healthcheck + lifespan)
```

> **O Tailwind CSS é compilado dentro do Docker build (multi-stage).**
> Não é necessário rodar `npm install` no VPS.

---

## Primeiro Deploy (setup inicial)

```bash
# No painel do Dokploy:
# 1. Criar novo projeto do tipo "Compose"
# 2. Apontar para o repositório GitHub
# 3. Branch: main
# 4. Copiar e preencher variáveis de ambiente (ver .env.example)
# 5. Clicar em Deploy

# Após o primeiro deploy, selar o banco como baseline do Alembic:
docker compose exec backend alembic stamp head
```

---

## Variáveis de Ambiente no Dokploy

No Dokploy, as variáveis são configuradas na aba **Environment** do projeto.
Copie o conteúdo do `.env.example` e preencha os valores reais.

> As variáveis de CI/CD (`VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`) são
> GitHub Secrets — usadas apenas pelo workflow de deploy manual de emergência.

---

## Deploy Manual de Emergência

Se o Dokploy não estiver respondendo, use o workflow manual:

```
GitHub → Actions → "Deploy to Production" → Run workflow
```

Ou via SSH direto:

```bash
ssh user@seu-vps
cd /etc/dokploy/compose/auto-tech-lith
git pull origin main
docker compose up -d --build --remove-orphans
docker compose exec backend alembic upgrade head
```

---

## Health Checks

```bash
# App + dependências
curl https://autotechlith.com/health

# Página de status pública
https://autotechlith.com/status

# Metrics Prometheus
curl -H "Authorization: Bearer $METRICS_TOKEN" https://autotechlith.com/api/v1/metrics
```

---

## Rollback

```bash
# Ver histórico de deploys no Dokploy (aba Deployments) e clicar em Rollback
# Ou manualmente:
git revert HEAD
git push origin main   # Dokploy faz o redeploy automaticamente
```

---

## Frontend Build

O build do Tailwind CSS acontece **automaticamente** no `docker build` (Dockerfile multi-stage):

1. Stage 1 (Node 20): `npm ci && npm run build:css` → gera `css/tailwind.min.css`
2. Stage 2 (Python 3.11): copia apenas o `.min.css` gerado, sem `node_modules`

**Não é necessário** rodar `npm install` ou `npm run build:css` no VPS.
