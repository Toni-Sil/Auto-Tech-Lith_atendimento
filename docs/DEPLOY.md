# Guia de Deploy Local (Windows + Docker + Ngrok)

Este guia foi adaptado para rodar o **Dify** no seu computador local (Windows), conectando-se à **Evolution API** que já está rodando.

---

## 1. Preparação

1. Certifique-se de que a **Evolution API** está rodando no Docker.
2. Verifique se o arquivo `.env` está configurado corretamente em `p:\agentes\.env`.

## 2. Iniciar o Dify

Abra o terminal (PowerShell ou CMD) na pasta `p:\agentes` e execute:

```powershell
docker compose -f docker-compose.dify.yml up -d
```

Isso vai subir o Dify na mesma rede da Evolution API (`evolution_evolution_network`).
Aguarde alguns minutos até que todos os containers estejam "started" ou "healthy".

## 3. Acessar o Dify

Abra no navegador: http://localhost:3001
*(Nota: Mudamos para a porta **3001** porque a 3000 já é usada pelo Evolution/Typebot Manager)*

- Crie sua conta de administrador.
- Senha inicial (se pedir): `AutoTech2026!`

## 4. Configurar Modelos e Agente

No painel do Dify (http://localhost:3001):

1. **Settings > Model Providers**:
   - Adicione sua **OpenAI API Key** (do arquivo .env).
   - Habilite **GPT-4o** e **Whisper**.

2. **Studio > Create App > Agent**:
   - Nome: `MAX - Auto Tech Lith`
   - Cole o **System Prompt** (arquivo `dify/agent-prompt.md`).
   - Habilite **Speech-to-Text**.
   - Em **Memory**: Habilite a "Conversation Memory" (Window size: 10-20). Isso já usa o Redis configurado.

3. **External Tools** (Edge Functions):
   - Adicione as 4 ferramentas conforme descrito no plano, importando o schema de `dify/openapi-tools.yaml`.
   - **URL do Servidor**: Como as Edge Functions estão na nuvem (Supabase), use as URLs reais (`https://lkobbhgmzppbhnevaycp.supabase.co/functions/v1...`).
   - **Auth**: Header `Authorization: Bearer <SUA_SUPABASE_ANON_KEY>`.
   - **Dica Ninja**: Ao adicionar `get-client` no Agente, mapeie o parâmetro `phone` para a variável **`sys.user_id`**. Assim, o Dify pega o número do Zap automaticamente.

4. **Publicar e Gerar Chave**:
   - Publique o agente.
   - Vá em **API Access** e crie uma chave de API para o Agente. Copie-a.

## 5. Conectar Evolution API ao Dify

Como ambos estão na mesma rede Docker, a Evolution consegue chamar o Dify diretamente pelo nome do container (`dify-api`).

Execute este comando no **Terminal do Windows** (PowerShell):

```powershell
# Substitua SUA_CHAVE_DIFY pela chave que você copiou no passo 4.
# A URL http://dify-api:5001/v1 funciona internamente no Docker.

Invoke-RestMethod -Uri "http://localhost:8080/dify/create/Lith%20Auto%20Tech" `
  -Method Post `
  -Headers @{ "apikey" = "8571bc192fc944648da72a68273099d87c4713fc930c41cb82494a00e41224a2"; "Content-Type" = "application/json" } `
  -Body (@{
    enabled = $true
    botType = "agent"
    apiUrl = "http://dify-api:5001/v1"
    apiKey = "SUA_CHAVE_DIFY"
    triggerType = "all"
    expire = 0
    keywordFinish = "#sair"
    delayMessage = 1000
    unknownMessage = "Desculpe, não entendi. Pode reformular?"
    listeningFromMe = $false
    stopBotFromMe = $false
    keepOpen = $true
  } | ConvertTo-Json)
```

## 6. Testar

1. Envie "Olá" para o WhatsApp conectado.
2. O agente deve perguntar sobre consentimento LGPD. Responda "Sim".
3. O Dify deve receber, processar e continuar o fluxo.
3. Envie um áudio.
4. Verifique se os dados estão sendo salvos no Supabase.

---

### Solução de Problemas

- **Erro de Rede**: Se a Evolution não conseguir contatar `http://dify-api:5001`, verifique se estão na mesma rede:
  `docker network inspect evolution_evolution_network` (deve listar containers evolution e dify).
- **Ngrok**: O Ngrok é usado apenas para o WhatsApp (Meta) enviar mensagens para a Evolution. A comunicação Evolution -> Dify é interna.
- **Erro 500 / Instabilidade**: Mantenha sempre o WhatsApp atualizado na Evolution API (Menu "Instances" > "Update WhatsApp Version") para evitar desconexões.
