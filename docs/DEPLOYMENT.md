# Deployment Guide

## Pre-requisites

- Docker + Docker Compose on VPS
- GitHub Secrets configured:
  - `VPS_HOST` — IP or domain
  - `VPS_USER` — SSH user (e.g. `root`)
  - `VPS_SSH_KEY` — Private SSH key

## First Deploy

```bash
# 1. Clone on VPS
git clone https://github.com/Toni-Sil/Auto-Tech-Lith_atendimento /opt/auto-tech-lith
cd /opt/auto-tech-lith

# 2. Copy and fill .env
cp .env.example .env
nano .env

# 3. Start services
docker compose up -d --build

# 4. CRITICAL: stamp existing DB as alembic baseline (run ONCE)
docker compose exec app alembic stamp head

# 5. Verify
curl http://localhost:8000/health
```

## Subsequent Deploys

All handled automatically by GitHub Actions on push to `main`.

```bash
# Manual deploy (if needed)
docker compose pull
docker compose up -d --build --remove-orphans
docker compose exec app alembic upgrade head
```

## Frontend Build (local dev)

```bash
cd frontend
npm install
npm run watch:css   # development
npm run build:css   # production build
```

## Environment Variables

See `.env.example` for all required variables.

## Health Check

- App: `GET /health`
- Metrics: `GET /api/v1/metrics`
- Database: verified on startup via Alembic
