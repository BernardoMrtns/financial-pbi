# Guia de Configuração - Telegram Bot

## Resumo das Alterações

O arquivo `telegrambot.py` foi refatorado para se integrar com a estrutura do projeto:

### ✅ Melhorias Implementadas

1. **Integração com Configurações Centralizadas**
   - Usa `config.py` para todas as constantes
   - Utiliza `SCHEMA_ABAS` para validar estrutura das abas
   - Token do bot configurado via variável de ambiente

2. **Serviços Compartilhados**
   - Usa `services/google_sheets.py` para conexão
   - Utiliza `utils/logging_config.py` para logging centralizado
   - Reutiliza funções de retry e tratamento de erros

3. **Qualidade do Código**
   - Type hints em todas as funções
   - Docstrings explicativas
   - Tratamento robusto de erros
   - Logging detalhado de operações

4. **Funcionalidades**
   - DataFrames com colunas validadas do schema
   - Melhor parsing de argumentos
   - Mensagens mais informativas
   - Comandos `/start` e `/help`

---

## Instalação e Configuração

### 1. Instalar Dependências

```bash
pip install -r requirements.txt
```

O `python-telegram-bot>=21.0` foi adicionado ao `requirements.txt`.

### 2. Obter Token do Telegram

1. Conversa com [@BotFather](https://t.me/botfather) no Telegram
2. Use `/newbot` para criar um novo bot
3. Copie o token fornecido

### 3. Configurar Variável de Ambiente

**Windows (PowerShell):**
```powershell
$env:TELEGRAM_BOT_TOKEN="seu_token_aqui"
```

**Windows (CMD):**
```cmd
set TELEGRAM_BOT_TOKEN=seu_token_aqui
```

**Linux/macOS:**
```bash
export TELEGRAM_BOT_TOKEN="seu_token_aqui"
```

### 4. Executar o Bot

```bash
python telegrambot.py
```

---

## Comandos Disponíveis

| Comando | Uso | Exemplo |
|---------|-----|---------|
| `/start` | Exibe menu de ajuda | `/start` |
| `/help` | Exibe menu de ajuda | `/help` |
| `/debito` | Registrar débito avulso | `/debito 100 Compra Padaria Alimentacao CC1` |
| `/receita` | Registrar receita | `/receita 5000 Salario Fixo Salario ContaCorrente` |
| `/cartao` | Registrar compra no cartão | `/cartao 250 Compras Gerais Alimentacao Nubank 1` |
| `/pix` | Registrar Pix parcelado | `/pix 1200 Celular Eletrônicos 200 12` |
| `/invest` | Registrar investimento | `/invest Bitcoin Compra 50000 0.001` |

---

## Estrutura dos Dados

### DebitoAvulso
```
/debito <valor> <descrição> <categoria> <conta>
```
Colunas: `Data, Descrição, Categoria, Valor, ContaSaída`

### Receitas
```
/receita <valor> <descrição> <categoria> <conta>
```
Colunas: `Data, Descrição, Categoria, Valor, ContaDestino`

### ComprasCartao
```
/cartao <valor> <descrição> <categoria> <cartão> <parcelas>
```
Colunas: `Data, Descrição, Categoria, Cartão, ValorTotal, Parcelas`

### PixParcelado
```
/pix <total> <descrição> <categoria> <entrada> <pagas>
```
Colunas: `Data, Descrição, Categoria, ValorTotal, ValorEntrada, QtdPagas`

### Investimentos
```
/invest <tipo> <operação> <valor> <quantidade>
```
Colunas: `Data, Tipo, Operação, Valor, Quantidade, QuantidadeBTC`

---

## Logging e Monitoramento

Os logs são salvos em `logs/financial-pbi.log` e exibidos no console.

**Exemplos de logs:**
- ✅ Operação bem-sucedida
- ❌ Erro no parsing de argumentos
- ⚠️ Erro de conexão com Google Sheets

---

## Tratamento de Erros

O bot trata automaticamente:
- ✅ Falta de argumentos
- ✅ Erros de conexão com Google Sheets
- ✅ Limites de rate do Google Sheets (retry automático)
- ✅ Timeout de requisições

---

## Troubleshooting

### "Token não configurado"
- Certifique-se que `TELEGRAM_BOT_TOKEN` está definido
- Reinicie o terminal após definir a variável

### "Erro ao conectar ao Google Sheets"
- Verifique se `credentials.json` existe
- Confira se o `SPREADSHEET_ID` está correto em `config.py`
- Teste a conexão rodando `main.py`

### "Aba não encontrada"
- A aba será criada automaticamente na primeira inserção
- Verifique se o nome da aba corresponde ao schema

---

## Desenvolvimento Futuro

Possíveis melhorias:
- [ ] Sistema de autenticação para usuários
- [ ] Relatórios mensais via bot
- [ ] Alertas de gastos
- [ ] Integração com webhooks
- [ ] Suporte a transações em lote

---

## Referências

- [python-telegram-bot Documentation](https://docs.python-telegram-bot.org/)
- [Google Sheets API](https://developers.google.com/sheets/api)
- Documentação local do projeto em `README.md`
