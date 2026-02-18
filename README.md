# BLAST Agent Architecture

Este projeto implementa a estrutura do agente "Assistente Central" usando a arquitetura BLAST.

## Estrutura de Arquivos

- `system_prompt.md`: Definição da Persona, Objetivos e Tom de Voz.
- `skills/`: Diretório contendo as habilidades modulares do agente.
  - `sales_flow.md`: Regras de negócio e fluxo de atendimento.
  - `json_formatter.md`: Schema obrigatório de resposta JSON.
  - `security.md`: Regras de segurança e limites de escopo.
- `main.py`: Script principal para simular o agente localmente (Mock do LLM).
- `services/mocks.py`: Simulação dos serviços externos (Supabase, Drive, Agenda).

## Como Executar

1. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```

2. Execute o agente:
   ```bash
   python main.py
   ```

3. Interaja no terminal simulando um cliente (ex: "Quero um lanche" ou "Preciso de insulfilm").

## Validação e Testes

O script inclui um modo de autoteste com cenários pré-definidos (Benchmark BLAST):

```bash
python main.py --test
```

Isso verificará:
1. **Contexto**: Desambiguação de nicho.
2. **Ferramenta**: Busca no Drive e loop de resposta.
3. **Segurança**: Bloqueio de alteração de chave Pix.

## Integração com n8n

Para integrar com n8n:
1. Copie o conteúdo de `system_prompt.md` e dos arquivos em `skills/` para compor o System Message do nó do LLM.
2. Configure o Output Parser para JSON seguindo o schema de `json_formatter.md`.
3. Mapeie as ações de `acao_sistema` para ferramentas/nós no n8n.
