import requests
import json
import sys
import os
from datetime import timedelta
sys.path.append(os.getcwd())

from src.utils.security import create_access_token

token = create_access_token(
    data={"sub": "admin123", "role": "admin"},
    expires_delta=timedelta(minutes=15)
)

url = "http://localhost:8000/api/profiles"

payload = {
    "name": "Test Profile Async",
    "agent_name_display": "Dr. Smith",
    "channel": "whatsapp",
    "niche": "geral",
    "tone": "neutro",
    "formality": "equilibrado",
    "autonomy_level": "equilibrada",
    "base_prompt": ("Você é um assistente virtual para uma clinica de cardiologia. "
                    "Seu objetivo principal é triagem e marcação de consultas preliminares. "
                    "Seja muito formal e educado."
                    "Colete o nome do paciente, cpf, data de nascimento e sintomas.")
}

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}

print("Sending POST request to create profile...")
try:
    response = requests.post(url, json=payload, headers=headers)
    print("Status:", response.status_code)
    try:
        data = response.json()
        print(json.dumps(data, indent=2))
        
        # Verify if auto-filled correctly
        auto_filled_niche = data.get("niche")
        auto_filled_objective = data.get("objective")
        print("Auto-filled Niche:", auto_filled_niche)
        print("Auto-filled Objective:", auto_filled_objective)
    except Exception as e:
        print("Response text:", response.text)
except Exception as req_err:
    print("Request failed:", req_err)

