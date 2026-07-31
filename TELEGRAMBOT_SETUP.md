# Guia de Configuração — Telegram Bot (com Mini App)

O `telegrambot.py` tem **paridade total** com o bot do Discord. Toda a UI
interativa é um **Telegram Mini App** — uma página estática (`docs/index.html`)
hospedada de graça no **GitHub Pages**. Não há servidor, domínio nem custo.

## Como funciona

- **Painel** = teclado persistente (aparece no `/start` e `/painel`).
- **Botões de formulário** (Receita, Débito, Cartão, PIX, Wishlist, Investir,
  Assinatura, Fatura, SQL) abrem o Mini App; ao enviar, os dados voltam ao bot
  via `WebApp.sendData()` e são gravados.
- **PIX Editar** e **Ass On/Off** leem o banco ao vivo: o bot busca a lista e
  reabre o Mini App já com os itens embutidos na URL, você escolhe e confirma.
- **SQL** devolve o resultado como **imagem PNG** (igual ao Discord).
- **Status / ETL / Limpar** executam direto no bot.
- Continuam funcionando os **comandos manuais** (`/debito`, `/receita`, …) e o
  **texto livre com IA** (ex.: *"15 no inter com lanche"*).
- **Apple Pay** permanece exclusivo do bot do Discord.

---

## 1. Ativar o GitHub Pages (passo único — obrigatório)

O Mini App precisa estar em HTTPS. O GitHub Pages faz isso de graça porque o
repositório é público.

1. Faça commit/push da pasta `docs/` (ela contém `index.html` e `.nojekyll`).
2. No GitHub, abra o repositório → **Settings** → **Pages**.
3. Em **Source**, escolha **Deploy from a branch**.
4. Em **Branch**, selecione **`main`** e a pasta **`/docs`** → **Save**.
5. Aguarde ~1 minuto e confirme que este endereço abre no navegador:

   ```
   https://bernardomrtns.github.io/financial-pbi/
   ```

   (Ao abrir fora do Telegram, os botões mostram um alerta em vez de gravar —
   isso é esperado. Dentro do Telegram eles enviam os dados ao bot.)

> Se um dia você usar outro repositório/usuário ou um domínio próprio, defina
> `MINIAPP_URL = "https://.../"` no `config.py` que o bot usa. Sem isso, o bot
> usa o Pages padrão acima.

---

## 2. Criar o bot no Telegram

1. Fale com [@BotFather](https://t.me/botfather) → `/newbot` → copie o **token**.
2. Descubra seu **user id** com [@userinfobot](https://t.me/userinfobot).

---

## 3. Configurar o `config.py`

O `config.py` é **gitignored** (fica só na sua máquina / no secret `CONFIG_PY`
do GitHub Actions). Ele precisa conter, no mínimo:

```python
TELEGRAM_TOKEN = "123456:AA..."      # token do BotFather
AUTHORIZED_USER_ID = 987654321        # seu id do @userinfobot
DB_URL = "postgresql+psycopg2://usuario:senha@host:5432/banco"
GEMINI_API_KEY = "sua_chave_gemini"   # texto livre com IA
# MINIAPP_URL = "https://.../"        # opcional, só se mudar de host
```

(Se você também roda o bot do Discord, mantenha `DISCORD_TOKEN` e
`DISCORD_AUTHORIZED_USER_ID` no mesmo arquivo.)

---

## 4. Instalar e executar

```bash
pip install -r requirements.txt
python telegrambot.py
```

No Telegram, envie `/start` — o painel aparece. Toque em **🟢 Receita** para
testar o Mini App.

---

## Comandos

| Comando | Uso |
|---|---|
| `/start`, `/painel` | Abre o painel (Mini App) |
| `/help` | Lista de comandos |
| `/debito`, `/receita` | `[valor] [conta] [categoria] [descrição]` |
| `/cartao` | `[total] [cartao] [parcelas] [categoria] [descrição]` |
| `/pix` | `[total] [entrada] [pagas] [categoria] [descrição]` |
| `/invest` | `[tipo] [operação] [valor] [qtd_cripto]` |
| `/wish_add` | `[preço] [nome_com_underline] [categoria] [prioridade]` |
| `/fatura_update` | `[cartão] [nova_data]` |
| `/pix_update` | `[id_compra] [qtd_pagas]` |
| `/ass_toggle` | `[nome_assinatura]` — alterna ativa/inativa |
| `/sql` | `[query]` — resultado como imagem |
| `/status` | Telemetria da VM |
| `/run_script` | Recalcular Fluxo de Caixa (ETL) |
| `/limpar` | Apaga as mensagens do bot no chat |

---

## Solução de problemas

- **Botão do Mini App abre página em branco / erro** → o Pages ainda não
  propagou (aguarde) ou a pasta `/docs` não foi selecionada em Settings → Pages.
- **"Bad Request: BUTTON_TYPE_INVALID" ao enviar o teclado** → a URL não é
  HTTPS válida; confirme o endereço do passo 1.
- **Mini App não grava nada** → o botão precisa ser do **teclado de respostas**
  (é o caso aqui). Botões inline não conseguem usar `sendData`.
- **PIX Editar / Ass On/Off vazios** → não há registros na tabela ainda.
- **`/status` com erro** → os comandos `free`/`df` são de Linux (a VM).

---

## Referências

- [Telegram Mini Apps](https://core.telegram.org/bots/webapps)
- [python-telegram-bot](https://docs.python-telegram-bot.org/)
- [GitHub Pages](https://docs.github.com/pages)
