# Guia de Configuração: Integração n8n (BLAST)

Este guia descreve a topologia e configuração para implementar o Agente BLAST no n8n.

## 1. Topologia Visual
O fluxo deve seguir esta estrutura:
`[WhatsApp Trigger]` -> `[Agente OpenAI (BLAST)]` -> `[JSON Parse]` -> `[Switch (Roteador)]`

### Ramificações do Switch:
- **Caminho A (Nenhuma Ação):** -> Responder no WhatsApp.
- **Caminho B (Buscar Drive):** -> `[Google Drive Node]` -> Voltar para o Agente (ou responder direto).
- **Caminho C (Agendar):** -> `[Supabase/Calendar]` -> Responder.

## 2. Configurando o Nodo de IA
Use o nodo **"Basic LLM Chain"** ou conecte um modelo de Chat a um nodo **"AI Agent"**.

**Prompt do Sistema (System Message):**
Você **NÃO** deve colar apenas um arquivo. Copie o conteúdo do arquivo `n8n_system_prompt.md` deste repositório e cole no campo "System Message". Ele já contém todas as Skills concatenadas.

## 3. Processando o JSON ("O Corpo")
Como o agente responde em JSON, precisamos parsear a string.

1. **Nodo Edit Fields (ou Code):**
   - Expressão: `{{ JSON.parse($json.content) }}`
   - *Nota: Ajuste `$json.content` para o campo onde a resposta da IA chega.*

2. **Nodo Switch (O Roteador):**
   - Configure para verificar a propriedade: `acao_sistema.ferramenta`
   - **Regra default:** Se igual a `nenhuma`, conecta ao nodo de resposta (WhatsApp).
   - **Regra 1:** Se igual a `buscar_drive`, conecta ao nodo Google Drive.
   - **Regra 2:** Se igual a `salvar_pedido`, conecta ao nodo Supabase.

## 4. Integração das Ferramentas
### Caminho `buscar_drive`:
- **Nodo Google Drive**
- **Operation:** List (Search)
- **Query String:** `name contains '{{ $json.acao_sistema.parametro }}'`
- **Loop:** Conecte a saída de volta a um nodo de resposta ou ao LLM para formatar a mensagem final.

### Caminho `salvar_pedido`:
- **Nodo Supabase**
- **Operation:** Insert
- **Mapping:** Mapeie `nome` e `telefone` do JSON para as colunas do banco.
