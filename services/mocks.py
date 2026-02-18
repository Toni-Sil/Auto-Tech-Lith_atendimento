import os

# Mock Database for Supabase
class SupabaseMock:
    def salvar_supabase(self, dados_json):
        # dados_json pode ser string ou dict, dependendo de como vem do "LLM"
        print(f"   [Supabase] Registrando dados: {dados_json}")
        return "Dados registrados com sucesso (ID: 9988)"

# Mock Google Drive
class DriveMock:
    def buscar_drive(self, termo):
        print(f"   [Drive] Pesquisando imagem por: '{termo}'...")
        # Simula delay ou processamento
        return f"https://drive.google.com/share/foto-{termo.replace(' ', '-')}.jpg"

# Mock Agenda
class AgendaMock:
    def verificar_agenda(self, data_ou_termo):
        print(f"   [Agenda] Consultando disponibilidade para: {data_ou_termo}")
        return "Disponível: 14:00, 16:30. Indisponível: 10:00."

# Service Factory
class ServiceContainer:
    def __init__(self):
        self.supabase = SupabaseMock()
        self.drive = DriveMock()
        self.agenda = AgendaMock()
    
    def executar(self, acao, parametro):
        """
        Hub central de execução de ferramentas
        """
        if acao == "buscar_drive":
            return self.drive.buscar_drive(parametro)
        elif acao == "verificar_agenda":
            return self.agenda.verificar_agenda(parametro)
        elif acao == "salvar_supabase":
            return self.supabase.salvar_supabase(parametro)
        else:
            return f"Erro: Ação '{acao}' não reconhecida pelo sistema."

services = ServiceContainer()
