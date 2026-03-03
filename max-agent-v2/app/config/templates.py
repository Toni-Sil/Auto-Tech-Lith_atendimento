"""
Notification Templates
Antigravity Skill: communication-design
"""

NOTIFICATION_TEMPLATES = {
    "12h": """Olá {nome}! Falta 12h para nosso briefing de {tipo_reuniao} (Amanhã às {hora}).

Para que eu possa me preparar, confirma que está tudo certo?

Responda com:
1️⃣ ou SIM para Confirmar
2️⃣ ou REAGENDAR se precisar mudar
3️⃣ ou CANCELAR se desistiu""",

    "6h": """{nome}, em 6h iniciamos nosso briefing!

Alguma dúvida de última hora? Pode mandar aqui 👇

Link do Zoom: {link_reuniao}""",

    "1h": """Começamos em 1 hora!

Irei te ligar ou acesse o link: {link_reuniao}

Até já! 🚀""",
    
    "confirmed": """Perfeito! Confirmado para amanhã às {hora}. Te enviarei o link 1h antes. Até lá!""",
    
    "reschedule_options": """Entendido. Aqui estão 3 horários alternativos para esta semana:
{opcoes}

Responda com o número da opção desejada.""",

    "internal_12h": """📅 **CONFIMAÇÃO DE BRIEFING (T-12h)**
Cliente: {nome}
Hora: {hora}
Status: {status}
Score: {score}/100
Nicho: {nicho}
Dor: {dor}

[Link WhatsApp](https://wa.me/{telefone})""",

    "internal_1h": """⏰ **COMEÇANDO EM 1 HORA!**
Cliente: {nome}
Link: {link_reuniao}

💡 Últimas msgs:
{contexto}"""
}
