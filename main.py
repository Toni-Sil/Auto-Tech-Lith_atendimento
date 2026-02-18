import os
import json
import logging
import requests
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, Request, HTTPException, Query
from pydantic import BaseModel, Field
from google.oauth2 import service_account
from googleapiclient.discovery import build
import google.generativeai as genai

# Configuração de Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONFIGURAÇÕES ---
CREDENTIALS_FILE = "credentials.json"
VERIFY_TOKEN = "minhasenhasecreta123" 
GEMINI_API_KEY = "AIzaSyAHMVgRNrbL67_0I_hmEikMgJ1ey1oiZ1A" 
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

# Configuração Gemini
genai.configure(api_key=GEMINI_API_KEY)

app = FastAPI(title="BLAST Agent Webhook")

# --- MODELOS PYDANTIC (WhatsApp Payload Simplificado) ---
class TextMessage(BaseModel):
    body: str

class Message(BaseModel):
    from_: str = Field(alias="from")
    id: str
    timestamp: str
    text: Optional[TextMessage] = None
    type: str

class ChangeValue(BaseModel):
    messaging_product: str
    metadata: Dict[str, Any]
    contacts: Optional[List[Dict[str, Any]]] = None
    messages: Optional[List[Message]] = None

class Change(BaseModel):
    value: ChangeValue
    field: str

class Entry(BaseModel):
    id: str
    changes: List[Change]

class WhatsAppWebhook(BaseModel):
    object: str
    entry: List[Entry]

# --- 2. INTEGRAÇÃO GOOGLE DRIVE ---
def buscar_foto_drive(termo: str) -> str:
    """
    Busca uma imagem no Google Drive contendo o termo no nome.
    Retorna o webViewLink da primeira correspondência.
    """
    logger.info(f"[DRIVE] Buscando por: {termo}")
    
    if not os.path.exists(CREDENTIALS_FILE):
        return f"ERRO: Arquivo {CREDENTIALS_FILE} não encontrado."

    try:
        creds = service_account.Credentials.from_service_account_file(
            CREDENTIALS_FILE, scopes=SCOPES
        )
        service = build('drive', 'v3', credentials=creds)

        # Query para buscar arquivos que contenham o termo no nome e sejam imagem
        query = f"name contains '{termo}' and mimeType contains 'image/' and trashed = false"
        
        results = service.files().list(
            q=query,
            pageSize=1,
            fields="nextPageToken, files(id, name, webViewLink, webContentLink)"
        ).execute()

        items = results.get('files', [])

        if not items:
            return f"Não encontrei nenhuma foto de '{termo}' no Drive."
        
        # Retorna o link da primeira foto encontrada
        return items[0].get('webViewLink')

    except Exception as e:
        logger.error(f"[DRIVE ERROR] {str(e)}")
        return f"Erro ao acessar Google Drive: {str(e)}"

# --- 3. CÉREBRO DO AGENTE (GEMINI LOGIC) ---
def carregar_skills(base_path: str = "skills") -> str:
    prompt_final = ""
    arquivos_prioritarios = ["security.md", "sales_flow.md", "json_formatter.md"]
    
    for arquivo in arquivos_prioritarios:
        caminho = os.path.join(base_path, arquivo)
        if os.path.exists(caminho):
            with open(caminho, "r", encoding="utf-8") as f:
                prompt_final += f"\n\n--- {arquivo} ---\n" + f.read()
    return prompt_final

def get_gemini_response(chat_session, message: str) -> Dict[str, Any]:
    """
    Envia mensagem para o Gemini e processa a resposta JSON.
    """
    try:
        response = chat_session.send_message(message)
        logger.info(f"Gemini Raw Response: {response.text}")
        return json.loads(response.text)
    except Exception as e:
        logger.error(f"Erro ao processar resposta do Gemini: {e}")
        return {
             "raciocinio": "Erro ao processar a resposta da IA.",
             "texto_resposta": "Desculpe, tive um erro interno. Tente novamente.",
             "acao_sistema": {"ferramenta": "nenhuma"}
        }

# --- 1. ROTAS DO WEBHOOK ---

@app.get("/webhook")
async def verify_webhook(
    mode: str = Query(alias="hub.mode"),
    token: str = Query(alias="hub.verify_token"),
    challenge: str = Query(alias="hub.challenge")
):
    """
    Verificação do Token (Meta Hub Challenge)
    """
    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("Webhook verificado com sucesso!")
        return int(challenge)
    raise HTTPException(status_code=403, detail="Token de verificação inválido")

@app.post("/webhook")
async def receive_message(payload: WhatsAppWebhook):
    """
    Recebimento de Mensagens
    """
    try:
        # Extrair dados básicos da primeira mensagem
        entry = payload.entry[0]
        change = entry.changes[0]
        value = change.value
        
        if not value.messages:
            return {"status": "ignored", "detail": "Nenhuma mensagem encontrada"}

        message = value.messages[0]
        
        # Ignora mensagens que não sejam texto (por enquanto)
        if message.type != "text":
            return {"status": "ignored", "detail": "Tipo de mensagem não suportado"}

        texto_usuario = message.text.body
        numero_cliente = message.from_

        logger.info(f"Mensagem de {numero_cliente}: {texto_usuario}")

        # 1. Configurar Modelo e Chat
        system_instruction = carregar_skills()
        model = genai.GenerativeModel(
            model_name='gemini-1.5-flash',
            system_instruction=system_instruction,
            generation_config={"response_mime_type": "application/json"}
        )
        
        # Inicia chat (sem histórico persistido por enquanto, stateless request)
        # TODO: Para conversas reais, implementar persistência de histórico (Redis/DB)
        chat = model.start_chat(history=[])

        # 2. Primeira Interação com Gemini
        decisao = get_gemini_response(chat, texto_usuario)
        
        acao_sistema = decisao.get("acao_sistema", {})
        ferramenta = acao_sistema.get("ferramenta")
        parametro = acao_sistema.get("parametro")
        texto_final = decisao.get("texto_resposta")

        # 3. Executar Ação (Busca Drive) se necessário
        if ferramenta == "buscar_drive" and parametro:
            logger.info("Acionando ferramenta: buscar_drive")
            resultado_drive = buscar_foto_drive(parametro)
            
            # 4. Devolver resultado para Gemini finalizar
            # Enviamos o resultado como se fosse uma "mensagem de sistema" ou continuação
            msg_tool = f"RESULTADO DA FERRAMENTA buscar_drive: {resultado_drive}. Agora finalize a resposta para o usuário."
            
            decisao_final = get_gemini_response(chat, msg_tool)
            texto_final = decisao_final.get("texto_resposta", "Aqui está o que encontrei.")

        # 5. Responder ao Usuário
        # EM PRODUÇÃO: Aqui entra a chamada requests.post para a API do WhatsApp
        if texto_final:
             enviar_whatsapp(numero_cliente, texto_final)

        logger.info(f"[RESPOSTA PARA {numero_cliente}]: {texto_final}")

        return {"status": "processed", "reply": texto_final}

    except Exception as e:
        logger.error(f"Erro ao processar webhook: {e}")
        return {"status": "error", "detail": str(e)}

# --- FUNÇÃO DE ENVIO REAL (Adicione isso no final do main.py) ---
def enviar_whatsapp(numero, texto):
    # ATENÇÃO: Preencha com seus dados do Painel da Meta
    WHATSAPP_TOKEN = "SEU_TOKEN_DE_ACESSO_TEMPORARIO_OU_PERMANENTE"
    PHONE_ID = "SEU_ID_DO_NUMERO_DE_TELEFONE"
    
    url = f"https://graph.facebook.com/v17.0/{PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "text",
        "text": {"body": texto}
    }
    
    try:
        r = requests.post(url, headers=headers, json=payload)
        logger.info(f"📡 Status Envio WhatsApp: {r.status_code}")
        if r.status_code != 200:
             logger.error(f"Erro detalhado WhatsApp: {r.text}")
    except Exception as e:
        logger.error(f"❌ Erro ao enviar: {e}")

# Para rodar:
# uvicorn main:app --reload
