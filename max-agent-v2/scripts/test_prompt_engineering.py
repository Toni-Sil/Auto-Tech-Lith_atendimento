import sys
import os

# Adiciona o diretório raiz ao PYTHONPATH
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.prompts import PromptManager

def main():
    manager = PromptManager()
    
    scenarios = [
        {
            "name": "Cenário 1: E-commerce de Moda (Cliente com Pressa)",
            "niche": "ecommerce_moda",
            "history": "Olá, preciso de um bot pra ontem. Meus clientes ficam perguntando tamanho toda hora.",
            "expected_tone": "Pressa/Direto"
        },
        {
            "name": "Cenário 2: Clínica de Estética (Cliente Inseguro)",
            "niche": "clinica_estetica",
            "history": "Oi... eu queria saber se funciona mesmo. Tenho medo de gastar e não dar certo. É seguro?",
            "expected_tone": "Inseguro/Autoridade"
        },
        {
            "name": "Cenário 3: Restaurante (Cliente Focado em Preço)",
            "niche": "restaurante_delivery",
            "history": "Quanto custa? É muito caro? Tem desconto pra fechar agora?",
            "expected_tone": "Preço/ROI"
        }
    ]
    
    print("=== INICIANDO TESTES DE PROMPT ENGINEERING ===\n")
    
    for scenario in scenarios:
        print(f"--- {scenario['name']} ---")
        prompt = manager.construct_system_prompt(
            company_niche=scenario['niche'],
            conversation_history=scenario['history']
        )
        
        # Verificações básicas
        if scenario['niche'] in prompt or "CONHECIMENTO DE NICHO" in prompt:
            print("✅ Nicho injetado corretamente")
        else:
            print("❌ FALHA: Nicho não encontrado")
            
        if "TOM DE VOZ DETECTADO" in prompt:
            print("✅ Detecção de tom acionada")
        else:
            print("❌ FALHA: Detecção de tom não funcionou")
            
        print("\nTRECHO DO PROMPT GERADO:")
        # Imprime apenas as partes dinâmicas para conferência visual
        start_idx = prompt.find("{{NICHE_CONTEXT}}") 
        if start_idx == -1: start_idx = prompt.find("## CONHECIMENTO DE NICHO")
        
        end_idx = prompt.find("## OBJETIVO")
        if start_idx != -1 and end_idx != -1:
             print(prompt[start_idx:end_idx].strip())
        else:
             print("(Não foi possível isolar o trecho dinâmico, verifique o debug completo se necessário)")
             
        print("\n" + "="*30 + "\n")

if __name__ == "__main__":
    main()
