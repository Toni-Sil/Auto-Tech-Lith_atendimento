# Estrutura Completa - Auto Tech Lith Customer Service Agent

## 📁 Arquitetura do Projeto

```
auto-tech-lith-agent/
│
├── .env.example                    # Template de variáveis de ambiente
├── requirements.txt                # Dependências Python
├── docker-compose.yml              # Orquestração de serviços
├── README.md                       # Documentação completa
│
├── src/
│   ├── __init__.py
│   ├── main.py                     # Entry point da aplicação
│   ├── config.py                   # Configurações centralizadas
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base_agent.py           # Classe base para agentes
│   │   ├── customer_service_agent.py # Agente principal de atendimento
│   │   └── triage_agent.py         # Agente de triagem
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── database.py             # ORM e configurações do BD
│   │   ├── customer.py             # Modelo de Cliente
│   │   ├── ticket.py               # Modelo de Ticket
│   │   ├── meeting.py              # Modelo de Reunião
│   │   └── conversation.py         # Modelo de Conversa
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── whatsapp_service.py     # Integração Evolution API
│   │   ├── llm_service.py          # GPT-4o mini
│   │   ├── telegram_service.py     # Notificações via Telegram
│   │   ├── ngrok_service.py        # Configuração ngrok
│   │   └── email_service.py        # Notificações via email (opcional)
│   │
│   ├── workflows/
│   │   ├── __init__.py
│   │   ├── customer_intake.py      # Fluxo de entrada de cliente
│   │   ├── triage_flow.py          # Fluxo de triagem
│   │   ├── briefing_meeting.py     # Fluxo de reunião de briefing
│   │   ├── proposal_meeting.py     # Fluxo de reunião de proposta
│   │   └── pos_proposal_triage.py  # Triagem pós-proposta
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py               # Rotas da API
│   │   ├── webhooks.py             # Webhooks (WhatsApp, Telegram)
│   │   └── middleware.py           # Autenticação e CORS
│   │
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── logger.py               # Sistema de logging
│   │   ├── validators.py           # Validações
│   │   ├── formatters.py           # Formatadores de dados
│   │   └── helpers.py              # Funções auxiliares
│   │
│   └── prompts/
│       ├── __init__.py
│       ├── system_prompts.py       # Prompts do sistema
│       ├── customer_service.py     # Prompts para atendimento
│       └── triage.py               # Prompts para triagem
│
├── frontend/
│   ├── index.html                  # Dashboard central
│   ├── css/
│   │   └── style.css               # Estilos
│   ├── js/
│   │   ├── main.js                 # Script principal
│   │   ├── api-client.js           # Cliente API
│   │   └── components.js           # Componentes UI
│   └── assets/
│       └── logo.png
│
├── tests/
│   ├── __init__.py
│   ├── test_agents.py
│   ├── test_services.py
│   └── test_workflows.py
│
└── scripts/
    ├── init_db.py                  # Inicializar banco de dados
    ├── seed_data.py                # Dados de teste
    └── deploy.sh                   # Script de deploy
```

## 🔄 Fluxo de Funcionamento

```
WhatsApp (Evolution API)
    ↓
    └─→ Webhook Trigger (ngrok)
        ↓
        └─→ Agente de Atendimento (GPT-4o mini)
            ├─→ Análise de Intent
            ├─→ Triagem Automática
            ├─→ Registro em BD (PostgreSQL)
            └─→ Agendamento de Reuniões
                ↓
                ├─→ Notification (Telegram)
                └─→ Dashboard Web (Central Admin)
```

## 🛠️ Stack Técnico

| Componente | Tecnologia |
|-----------|-------------|
| **Backend** | Python 3.11+ |
| **Framework** | FastAPI |
| **BD Principal** | PostgreSQL |
| **ORM** | SQLAlchemy |
| **IA** | GPT-4o mini (OpenAI) |
| **WhatsApp** | Evolution API |
| **Notificações** | Telegram Bot API |
| **Webhook** | ngrok |
| **Frontend** | HTML5 + Vanilla JS |
| **Containerização** | Docker + Docker Compose |
| **Async** | asyncio + aiohttp |
| **Logging** | Python logging + structlog |

## ⚙️ Configuração Rápida

### 1. Clone e Setup
```bash
git clone <repo>
cd auto-tech-lith-agent
python -m venv venv
source venv/bin/activate  # ou `venv\Scripts\activate` no Windows
pip install -r requirements.txt
```

### 2. Variáveis de Ambiente
```bash
cp .env.example .env
# Editar .env com suas credenciais
```

### 3. Banco de Dados
```bash
python scripts/init_db.py
```

### 4. Iniciar Aplicação
```bash
# Desenvolvimento
python -m src.main
# Produção (Docker)
docker-compose up -d
```

### 5. Acessar Dashboard
- **Frontend**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **ngrok URL**: Será exibida no console

## 📊 Endpoints API Principais

### Clientes
- `GET /api/customers` - Lista de clientes
- `GET /api/customers/{id}` - Detalhes do cliente
- `POST /api/customers` - Criar cliente
- `PUT /api/customers/{id}` - Atualizar cliente
- `DELETE /api/customers/{id}` - Deletar cliente

### Tickets
- `GET /api/tickets` - Lista de tickets
- `POST /api/tickets` - Criar ticket
- `PUT /api/tickets/{id}` - Atualizar ticket

### Reuniões
- `GET /api/meetings` - Lista de reuniões
- `POST /api/meetings` - Agendar reunião
- `PUT /api/meetings/{id}` - Atualizar reunião

### Webhooks
- `POST /api/webhooks/whatsapp` - Webhook WhatsApp
- `POST /api/webhooks/telegram` - Webhook Telegram

## 📝 Funcionalidades do Agente

### ✅ Implementado

1. **Atendimento Initial**
   - Recebe mensagens via WhatsApp
   - Identifica intent do cliente
   - Responde automaticamente

2. **Triagem Inteligente**
   - Classifica tipo de demanda
   - Prioriza tickets
   - Roteia para equipe correta

3. **Gestão de Clientes**
   - Registro automático em BD
   - Perfil com histórico completo
   - Histórico de interações

4. **Agendamento de Reuniões**
   - Propõe horários
   - Confirma automaticamente
   - Envia lembretes via Telegram

5. **Reunião de Briefing**
   - Coleta informações do cliente
   - Estrutura demanda
   - Prepara para proposta

6. **Reunião de Proposta**
   - Apresenta soluções
   - Coleta feedback
   - Converte em contrato

7. **Triagem Pós-Proposta**
   - Avalia feedback
   - Triagem de objeções
   - Próximos passos

### 🔄 Fluxos Automatizados
**Início da Conversa** → Triagem → Agendamento Briefing → Reunião Briefing → Agendamento Proposta → Reunião Proposta → Triagem Final

## 🔐 Segurança

- ✅ Validação de entrada em todos endpoints
- ✅ Rate limiting por IP
- ✅ Autenticação opcional (JWT ready)
- ✅ Hash de senhas (bcrypt)
- ✅ CORS configurável
- ✅ Variáveis de ambiente para secrets
- ✅ Logging de auditoria

## 📈 Monitoramento

- ✅ Logs estruturados
- ✅ Métricas de performance
- ✅ Rastreamento de erros
- ✅ Dashboard de status
- ✅ Alertas via Telegram

## 🚀 Deploy

### Local (Desenvolvimento)
```bash
python -m src.main
```

### Docker Compose
```bash
docker-compose up -d
```

### Cloud (Recomendado)
- Railway.app
- Render.com
- Replit
- Coolify (auto-hospedagem)

---

**Desenvolvido para: Auto Tech Lith**
**Última atualização: Fevereiro 2026**
