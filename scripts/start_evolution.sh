#!/bin/bash
# =============================================================================
# Auto Tech Lith - Script de inicialização dos serviços Docker
# Evolution API + PostgreSQL + Redis
# =============================================================================

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.yml"
ENV_FILE="$PROJECT_DIR/.env"

# Cores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[AVISO]${NC} $1"; }
log_error()   { echo -e "${RED}[ERRO]${NC} $1"; exit 1; }

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║      Auto Tech Lith - Iniciando Serviços         ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"
echo ""

# Verifica se o Docker está disponível
if ! docker info > /dev/null 2>&1; then
    log_error "Docker não está acessível. Execute: sudo usermod -aG docker \$USER && newgrp docker"
fi

# Carrega variáveis de ambiente
if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
    log_success "Variáveis de ambiente carregadas"
else
    log_error "Arquivo .env não encontrado em $ENV_FILE"
fi

# 1. Sobe PostgreSQL e Redis
log_info "Iniciando PostgreSQL e Redis..."
docker compose -f "$COMPOSE_FILE" up -d postgres redis
sleep 5

# 2. Cria o database da Evolution API (se não existir)
log_info "Criando banco de dados 'evolution' (se não existir)..."
docker exec auto_tech_postgres psql -U "${DB_USER:-admin}" -d "${DB_NAME:-auto_tech_lith}" -tc \
    "SELECT 1 FROM pg_database WHERE datname='${EVOLUTION_DB_NAME:-evolution}'" \
    | grep -q 1 || \
    docker exec auto_tech_postgres psql -U "${DB_USER:-admin}" -d "${DB_NAME:-auto_tech_lith}" \
    -c "CREATE DATABASE ${EVOLUTION_DB_NAME:-evolution};"
log_success "Banco 'evolution' pronto"

# 3. Sobe a Evolution API
log_info "Iniciando Evolution API..."
docker compose -f "$COMPOSE_FILE" up -d evolution_api
sleep 5

# 4. Verifica status
log_info "Verificando status dos serviços..."
echo ""
docker compose -f "$COMPOSE_FILE" ps

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✅ Serviços iniciados com sucesso!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo ""
echo -e "  📡 Evolution API:  ${BLUE}http://localhost:8080${NC}"
echo -e "  📚 Manager UI:     ${BLUE}http://localhost:8080/manager${NC}"
echo -e "  🗄️  PostgreSQL:     ${BLUE}localhost:5432${NC}"
echo -e "  🔴 Redis:          ${BLUE}localhost:6379${NC}"
echo ""
echo -e "  🔑 API Key: ${YELLOW}${EVOLUTION_API_KEY}${NC}"
echo ""
echo -e "  Para ver logs:     ${YELLOW}docker compose logs -f evolution_api${NC}"
echo -e "  Para parar tudo:   ${YELLOW}docker compose down${NC}"
echo ""
