"""
Tool Definitions for OpenAI Function Calling
Matches schemas in dify/openapi-tools.yaml
Antigravity Skill: prompt-engineering
"""

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "registrar_cliente",
            "description": "Registra ou atualiza dados de um cliente. Use quando o usuário fornecer Nome, Empresa e Nicho.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {
                        "type": "string",
                        "description": "Telefone do cliente com DDD (apenas números)"
                    },
                    "name": {
                        "type": "string",
                        "description": "Nome completo do cliente"
                    },
                    "company": {
                        "type": "string",
                        "description": "Nome da empresa"
                    },
                    "niche": {
                        "type": "string",
                        "description": "Nicho de atuação"
                    },
                    "email": {
                        "type": "string",
                        "description": "E-mail profissional do cliente"
                    },
                    "pain_point": {
                        "type": "string",
                        "description": "Dor principal identificada"
                    }
                },
                "required": ["phone", "name", "company"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "horarios_disponiveis",
            "description": "Consulta horários disponíveis para agendamento.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Data no formato YYYY-MM-DD"
                    }
                },
                "required": ["date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "agendar_reuniao",
            "description": "Agenda uma reunião final.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {"type": "string"},
                    "datetime": {"type": "string", "description": "ISO 8601"},
                    "type": {"type": "string", "enum": ["briefing", "proposta"]}
                },
                "required": ["phone", "datetime", "type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "confirmar_agendamento",
            "description": "Confirma um agendamento pendente para o cliente.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {
                        "type": "string",
                        "description": "Número de telefone do cliente"
                    }
                },
                "required": ["phone"]
            }
        }
    }
]
