from datetime import datetime
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Optional

import pandas as pd
from telegram import Update
from telegram.error import TimedOut, NetworkError
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest

from config import (
    SCHEMA_ABAS,
    COLUNAS_SHEETS,  # Importe o novo dicionário
    STATUS_PAGO,
    TIPO_ENTRADA,
    TIPO_SAIDA,
)
from services.google_sheets import (
    adicionar_linha_aba,
    carregar_worksheet_safe,
    conectar_google_sheets,
    salvar_aba,
)
from services.database import adicionar_linha_db, atualizar_tabela_completa
from utils.logging_config import get_logger
from utils.data_utils import (
    converter_data_flexivel,
    converter_numero_flexivel,
    normalizar_nome_cartao,
)

logger = get_logger(__name__)

# Variáveis globais inicializadas na startup
spreadsheet = None

# Usuário autorizado a usar o bot
AUTHORIZED_USER_ID = 1139123773
AUTHORIZED_USERNAME = "bernardo_mrtns"


def _get_hoje():
    """Retorna a data/hora atual como `pandas.Timestamp` (preserva tipo datetime)."""
    return pd.Timestamp.now()


async def _is_authorized(update: Update) -> bool:
    """Valida se o comando veio do usuário autorizado."""
    user = update.effective_user
    message = update.effective_message

    if user is None:
        if message:
            await message.reply_text("Acesso negado.")
        logger.warning("Comando sem usuário identificado foi bloqueado.")
        return False

    incoming_username = (user.username or "").lstrip("@").lower()
    expected_username = AUTHORIZED_USERNAME.lower()

    is_allowed = (
        user.id == AUTHORIZED_USER_ID
        and incoming_username == expected_username
    )

    if not is_allowed:
        if message:
            await message.reply_text("Acesso negado. Este bot é privado.")
        logger.warning(
            "Acesso bloqueado. user_id=%s username=%s first_name=%s last_name=%s",
            user.id,
            user.username,
            user.first_name,
            user.last_name,
        )
        return False

    return True


# --- HANDLERS ---


async def debito(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler para registrar débito avulso."""
    try:
        if not await _is_authorized(update):
            return
        if not context.args or len(context.args) < 4:
            await update.message.reply_text(
                "Erro. Use: /debito <valor> <descrição> <categoria> <conta>"
            )
            return

        valor = context.args[0]
        desc = " ".join(context.args[1:-2])
        cat = context.args[-2]
        conta = context.args[-1]

        cols = COLUNAS_SHEETS["DebitoAvulso"]
        data_dict = {
            cols["data"]: datetime.now().strftime("%d/%m/%Y"),
            cols["descricao"]: desc,
            cols["categoria"]: cat,
            cols["valor"]: valor,
            cols["conta"]: conta,
        }

        adicionar_linha_aba(spreadsheet, "DebitoAvulso", data_dict)
        adicionar_linha_db("DebitoAvulso", pd.DataFrame([data_dict]))
        logger.info(f"Débito registrado: {desc} - R${valor}")
        await update.message.reply_text(f"✅ Débito salvo: {desc} (R${valor})")
    except Exception as e:
        logger.error(f"Erro ao registrar débito: {e}")
        await update.message.reply_text(
            f"Erro ao salvar débito. Use: /debito <valor> <descrição> <categoria> <conta>"
        )


async def receita(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler para registrar receita."""
    try:
        if not await _is_authorized(update):
            return
        if not context.args or len(context.args) < 4:
            await update.message.reply_text(
                "Erro. Use: /receita <valor> <descrição> <categoria> <conta>"
            )
            return

        valor = context.args[0]
        desc = " ".join(context.args[1:-2])
        cat = context.args[-2]
        conta = context.args[-1]

        cols = COLUNAS_SHEETS["Receitas"]
        data_dict = {
            cols["data"]: datetime.now().strftime("%d/%m/%Y"),
            cols["descricao"]: desc,
            cols["categoria"]: cat,
            cols["valor"]: valor,
            cols["conta"]: conta,
        }

        adicionar_linha_aba(spreadsheet, "Receitas", data_dict)
        adicionar_linha_db("Receitas", pd.DataFrame([data_dict]))
        logger.info(f"Receita registrada: {desc} - R${valor}")
        await update.message.reply_text(f"✅ Receita salva: {desc} (R${valor})")
    except Exception as e:
        logger.error(f"Erro ao registrar receita: {e}")
        await update.message.reply_text(
            f"Erro ao salvar receita. Use: /receita <valor> <descrição> <categoria> <conta>"
        )


async def cartao_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler para registrar compra no cartão."""
    try:
        if not await _is_authorized(update):
            return
        if not context.args or len(context.args) < 5:
            await update.message.reply_text(
                "Erro. Use: /cartao <valor> <descrição> <categoria> <cartão> <parcelas>"
            )
            return

        valor = context.args[0]
        desc = " ".join(context.args[1:-3])
        cat = context.args[-3]
        cart = context.args[-2]
        parcelas = context.args[-1]

        cols = COLUNAS_SHEETS["ComprasCartao"]
        data_dict = {
            cols["data"]: datetime.now().strftime("%d/%m/%Y"),
            cols["descricao"]: desc,
            cols["categoria"]: cat,
            cols["cartao"]: normalizar_nome_cartao(cart),
            cols["valor_total"]: valor,
            cols["parcelas"]: parcelas,
        }

        adicionar_linha_aba(spreadsheet, "ComprasCartao", data_dict)
        adicionar_linha_db("ComprasCartao", pd.DataFrame([data_dict]))
        logger.info(f"Compra registrada: {desc} no {cart} - R${valor}")
        await update.message.reply_text(
            f"✅ Compra salva: {desc}\nCartão: {cart}\nValor: R${valor}\nParcelas: {parcelas}"
        )
    except Exception as e:
        logger.error(f"Erro ao registrar compra no cartão: {e}")
        await update.message.reply_text(
            f"Erro ao salvar compra. Use: /cartao <valor> <descrição> <categoria> <cartão> <parcelas>"
        )


async def pix_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler para registrar Pix parcelado."""
    try:
        if not await _is_authorized(update):
            return
        if not context.args or len(context.args) < 5:
            await update.message.reply_text(
                "Erro. Use: /pix <total> <descrição> <categoria> <entrada> <pagas>"
            )
            return

        total = context.args[0]
        desc = " ".join(context.args[1:-3])
        cat = context.args[-3]
        entrada = context.args[-2]
        pagas = context.args[-1]

        cols = COLUNAS_SHEETS["PixParcelado"]
        data_dict = {
            cols["data"]: datetime.now().strftime("%d/%m/%Y"),
            cols["descricao"]: desc,
            cols["categoria"]: cat,
            cols["valor_total"]: total,
            cols["valor_entrada"]: entrada,
            cols["qtd_pagas"]: pagas,
        }

        adicionar_linha_aba(spreadsheet, "PixParcelado", data_dict)
        adicionar_linha_db("PixParcelado", pd.DataFrame([data_dict]))
        logger.info(f"Pix parcelado registrado: {desc} - R${total}")
        await update.message.reply_text(
            f"✅ Pix parcelado salvo: {desc}\nTotal: R${total}\nEntrada: R${entrada}\nParceladas: {pagas}"
        )
    except Exception as e:
        logger.error(f"Erro ao registrar Pix parcelado: {e}")
        await update.message.reply_text(
            f"Erro ao salvar Pix. Use: /pix <total> <descrição> <categoria> <entrada> <pagas>"
        )


async def pagarpix_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Atualiza a quantidade de parcelas pagas de um Pix Parcelado"""
    if not await _is_authorized(update):
        return

    if not context.args:
        await update.message.reply_text("Uso: /pagarpix \"Nome do Item\" [parcelas]")
        return

    # Parsing robusto para nomes com espaços entre aspas
    try:
        args_str = " ".join(context.args)
        parsed_args = shlex.split(args_str)
        item_name = parsed_args[0]
        qtd_manual = int(parsed_args[1]) if len(parsed_args) > 1 else None
    except Exception:
        await update.message.reply_text("❌ Erro nos argumentos. Use aspas para nomes compostos.")
        return

    aba_nome = "PixParcelado"
    # Obtém os nomes reais das colunas da planilha
    cols_map = COLUNAS_SHEETS[aba_nome]
    col_item = cols_map["descricao"]   # ex: "Descricao"
    col_pagas = cols_map["qtd_pagas"]  # ex: "QtdPagas"

    try:
        ws = carregar_worksheet_safe(spreadsheet, aba_nome)
        dados = ws.get_all_records()
        if not dados:
            await update.message.reply_text(f"❌ A aba {aba_nome} está vazia ou não foi encontrada.")
            return

        df = pd.DataFrame(dados)

        if col_item not in df.columns or col_pagas not in df.columns:
            await update.message.reply_text(f"❌ Erro de estrutura: Colunas '{col_item}' ou '{col_pagas}' não encontradas.")
            return

        # Procura o item na coluna de descrição (conteúdo parcial, case-insensitive)
        mask = df[col_item].astype(str).str.contains(item_name, case=False, na=False)
        indices = df.index[mask].tolist()

        if not indices:
            await update.message.reply_text(f"❓ Item '{item_name}' não encontrado na aba {aba_nome}.")
            return

        idx = indices[0]
        nome_completo = df.at[idx, col_item]

        # Atualiza o valor
        if qtd_manual is not None:
            nova_qtd = qtd_manual
        else:
            valor_atual = str(df.at[idx, col_pagas]).replace(",", ".")
            nova_qtd = int(float(valor_atual)) + 1

        df.at[idx, col_pagas] = nova_qtd

        # Sincroniza ambos os sistemas
        salvar_aba(spreadsheet, aba_nome, df)
        atualizar_tabela_completa(aba_nome, df)

        await update.message.reply_text(f"✅ Pagamento de '{nome_completo}' atualizado para {nova_qtd} parcelas.")

    except Exception as e:
        logger.error(f"Erro no pagarpix: {e}")
        await update.message.reply_text(f"❌ Erro ao processar: {str(e)}")


async def invest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler para registrar investimento."""
    try:
        if not await _is_authorized(update):
            return

        # Log raw message and parsed args for debugging
        msg_text = "" if update.message is None else update.message.text or ""
        logger.debug("/invest raw text: %s | context.args: %s", msg_text, context.args)

        args = context.args or []
        if len(args) < 3:
            # Try to parse from raw text (handles quoting and extra spaces)
            rest = msg_text.lstrip()
            # remove leading command part
            if rest.startswith("/invest"):
                rest = rest[len("/invest"):].strip()
            # remove bot username suffix if present
            if rest.startswith("@"):
                # unlikely, but keep safe
                parts = rest.split(maxsplit=1)
                rest = parts[1] if len(parts) > 1 else ""
            try:
                args = shlex.split(rest)
            except Exception:
                args = rest.split()

        # Minimum required: tipo, operacao, valor
        if len(args) < 3:
            await update.message.reply_text(
                "Erro. Use: /invest <tipo> <operação> <valor> <quantidade>"
            )
            return

        tipo = args[0]
        oper = args[1]
        valor = args[2]

        # If investment is CDI, quantidade is optional and always 0
        if tipo.strip().lower() == "cdi":
            qtd = "0"
        else:
            if len(args) < 4:
                await update.message.reply_text(
                    "Erro. Use: /invest <tipo> <operação> <valor> <quantidade>"
                )
                return
            qtd = args[3]

        # Note: Investimentos tem colunas: DataHora, Tipo, Operacao, Valor, QuantidadeCripto
        cols = COLUNAS_SHEETS["Investimentos"]
        data_dict = {
            cols["datahora"]: pd.Timestamp.now().strftime("%d/%m/%Y %H:%M:%S"),
            cols["tipo"]: tipo,
            cols["operacao"]: oper,
            cols["valor"]: valor,
            cols["quantidade_cripto"]: qtd,
        }

        try:
            # deixar a normalização para adicionar_linha_db
            adicionar_linha_aba(spreadsheet, "Investimentos", data_dict)
            adicionar_linha_db("Investimentos", pd.DataFrame([data_dict]))
            logger.info(f"Investimento registrado: {tipo} {oper} - R${valor}")
            await update.message.reply_text(
                f"✅ Investimento salvo: {tipo}\nOperação: {oper}\nValor: R${valor}\nQuantidade: {qtd}"
            )
        except Exception as e:
            logger.exception("Erro ao registrar investimento: %s", e)
            await update.message.reply_text(
                f"Erro ao processar valores do investimento: {e}"
            )
    except Exception as e:
        logger.error(f"Erro ao registrar investimento: {e}")
        await update.message.reply_text(
            f"Erro ao salvar investimento. Use: /invest <tipo> <operação> <valor> <quantidade>"
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler para comando /start."""
    if not await _is_authorized(update):
        return

    help_text = (
        "🤖 *Bot de Controle Financeiro*\n\n"
        "*Como usar:*\n\n"
        
        "`/debito valor descricao categoria conta`\n"
        "_Ex: /debito 50 Mercado Alimentação Nubank_\n\n"
        
        "`/receita valor descricao categoria conta`\n"
        "_Ex: /receita 3000 Salário Trabalho Inter_\n\n"
        
        "`/cartao valor descricao categoria cartao parcelas`\n"
        "_Ex: /cartao 1200 Notebook Eletrônicos Nubank 12_\n\n"
        
        "`/pix total descricao categoria entrada qtdPagas`\n"
        "_Ex: /pix 500 Celular Eletrônicos 100 1_\n\n"

        "`/pagarpix \"Nome do Item\" [qtd_pagas]`\n"
        "_Ex: /pagarpix \"Celular\" (adiciona 1 parcela)_\n"
        "_Ex: /pagarpix \"Celular\" 3 (define exatamente 3 parcelas)_\n\n"
        
        "`/invest tipo operacao valor quantidade`\n"
        "_Ex: /invest BTC Aporte 1000 0.02_\n"
        "_Ex: /invest CDI Aporte 1000 0_\n\n"

        "`/run_script` - Executa o main.py em segundo plano\n\n"
        
        "`/help` - Exibir esta mensagem"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler para comando /help."""
    if not await _is_authorized(update):
        return

    await start(update, context)


async def run_script_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler para executar o main.py em segundo plano."""
    if not await _is_authorized(update):
        return

    script_path = Path(__file__).resolve().with_name("main.py")

    if not script_path.exists():
        await update.message.reply_text("Erro: main.py não foi encontrado.")
        return

    try:
        process = subprocess.Popen(
            [sys.executable, str(script_path)],
            cwd=str(script_path.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        logger.info("main.py iniciado pelo Telegram. pid=%s", process.pid)
        await update.message.reply_text(
            f"✅ main.py iniciado em segundo plano. PID: {process.pid}"
        )
    except Exception as e:
        logger.error("Erro ao iniciar main.py: %s", e, exc_info=True)
        await update.message.reply_text(f"Erro ao iniciar main.py: {e}")


def main() -> None:
    """Inicia o bot do Telegram."""
    import os
    from config import (
        TELEGRAM_READ_TIMEOUT,
        TELEGRAM_REQUEST_TIMEOUT,
    )
    global spreadsheet

    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not telegram_token:
        logger.error("TELEGRAM_BOT_TOKEN não está definido nas variáveis de ambiente")
        raise ValueError(
            "TELEGRAM_BOT_TOKEN não está configurado. "
            "Configure a variável de ambiente com seu token do Telegram."
        )

    logger.info("Iniciando bot do Telegram")
    
    # Inicializar conexão com Google Sheets
    try:
        spreadsheet = conectar_google_sheets()
        logger.info("Conectado com sucesso ao Google Sheets")
    except Exception as e:
        logger.error(f"Erro ao conectar ao Google Sheets: {e}")
        raise

    # Configurar request com timeouts maiores para Telegram
    request = HTTPXRequest(
        connect_timeout=TELEGRAM_REQUEST_TIMEOUT,
        read_timeout=TELEGRAM_READ_TIMEOUT,
        write_timeout=TELEGRAM_REQUEST_TIMEOUT,
        pool_timeout=TELEGRAM_REQUEST_TIMEOUT,
    )
    
    app = ApplicationBuilder().token(telegram_token).request(request).build()

    # Adicionar handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("debito", debito))
    app.add_handler(CommandHandler("receita", receita))
    app.add_handler(CommandHandler("cartao", cartao_cmd))
    app.add_handler(CommandHandler("pix", pix_cmd))
    app.add_handler(CommandHandler("pagarpix", pagarpix_cmd))
    app.add_handler(CommandHandler("invest", invest_cmd))
    app.add_handler(CommandHandler("run_script", run_script_cmd))

    logger.info("Bot iniciado e aguardando mensagens...")
    logger.info(f"Timeout de requisição: {TELEGRAM_REQUEST_TIMEOUT}s")
    logger.info(f"Timeout de leitura: {TELEGRAM_READ_TIMEOUT}s")
    
    try:
        app.run_polling(
            allowed_updates=["message", "edited_message"],
            bootstrap_retries=5,
        )
    except (TimedOut, NetworkError) as e:
        logger.error(f"Erro de conexão ao Telegram: {e}")
        logger.error("Verifique sua conexão com a internet e o token do bot")
        raise
    except KeyboardInterrupt:
        logger.info("Bot interrompido pelo usuário")
    except Exception as e:
        logger.error(f"Erro inesperado: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()