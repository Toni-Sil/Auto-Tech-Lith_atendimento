# Funcionalidades do Agente Auto Tech Lith (MAX)

Este documento resume tudo o que o seu agente **MAX** é capaz de fazer com a infraestrutura atual implementada.

## 1. Inteligência Conversacional (Cérebro)
- **Motor de IA**: Utiliza **GPT-4o**, capaz de entender conversas complexas, ironia e contexto de negócios.
- **Personalidade**: Configurado como um especialista em automação e tecnologia da Auto Tech Lith.
- **Memória**: Mantém o contexto da conversa (lembra o nome e a empresa citados anteriormente).

## 2. Processamento de Voz (Áudio)
- **Transcrição Automática**: O cliente pode enviar áudio de qualquer duração no WhatsApp.
- **Tecnologia**: Usa OpenAI **Whisper** para converter voz em texto com altíssima precisão.
- **Resposta**: O agente "lê" o áudio e responde em texto naturalmente.

## 3. Gestão de Clientes (CRM)
O agente atua proativamente salvando dados no **Supabase** (seu banco de dados):
- **Registro Automático**: Coleta Nome, Telefone e Empresa durante a conversa.
- **Enriquecimento**: Identifica o Nicho e a "Dor Principal" do cliente baseando-se no diálogo.
- **Reconhecimento**: Se o cliente voltar a falar, o agente consulta o banco e o chama pelo nome (`get-client`).

## 4. Agendamento Inteligente
Fluxo de agendamento 100% automatizado, sem conflitos:
- **Consulta de Agenda**: Verifica horários livres em tempo real (`available-slots`).
- **Bloqueio de Horário**: Garante que não haja duas reuniões no mesmo horário.
- **Tipos de Reunião**:
  - **Briefing**: 30 minutos (primeiro contato).
  - **Proposta**: 60 minutos (apresentação de solução).
- **Confirmação**: Envia os detalhes da reunião confirmada via WhatsApp.

## 5. Integração WhatsApp
- **Conectividade**: Funciona direto no número oficial da empresa via **Evolution API**.
- **Infraestrutura**: Roda no seu computador (Docker) com conexão segura via Ngrok.
