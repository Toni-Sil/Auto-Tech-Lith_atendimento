import sys
import os

# Adiciona diretório raiz no path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.tasks.followup import send_confirmation_email_task, send_whatsapp_reminder_task, send_feedback_email_task
from app.services.email_service import EmailService

# Mocking EmailService for testing without actually sending (optional, but good for local dev without keys)
# For this verify script, we want to try to send if keys are present, or just verify task execution.

def test_tasks_direct():
    print("=== TESTANDO TASKS (EXECUÇÃO DIRETA) ===")
    
    email = "teste@exemplo.com"
    phone = "5511999999999"
    meeting_details = {"time": "2024-12-25 10:00", "link": "https://meet.google.com/test"}
    
    print(f"1. Testando Email de Confirmação para {email}...")
    try:
        # Chamando a função diretamente (sem .delay) para ver se erro ocorre
        send_confirmation_email_task(email, meeting_details)
        print("✅ Task de Email executada com sucesso (Verifique logs/Resend)")
    except Exception as e:
        print(f"❌ Erro na task de email: {e}")

    print(f"\n2. Testando WhatsApp para {phone}...")
    try:
        send_whatsapp_reminder_task(phone, "Teste de Lembrete: Reunião em breve!")
        print("✅ Task de WhatsApp executada com sucesso")
    except Exception as e:
        print(f"❌ Erro na task de WhatsApp: {e}")

if __name__ == "__main__":
    test_tasks_direct()
