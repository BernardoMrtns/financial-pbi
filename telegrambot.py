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
    STATUS_PAGO,
    TIPO_ENTRADA,
    TIPO_SAIDA,
)
from services.google_sheets import (
    adicionar_linha_aba,
    carregar_worksheet_safe,
    conectar_google_sheets,
)
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

        # Criar DataFrame com as colunas do schema
        df = pd.DataFrame(
            [[_get_hoje(), desc, cat, valor, conta]],
            columns=SCHEMA_ABAS["DebitoAvulso"]
        )
        # Normalizações: Data como date-only, Valor numeric, categoria limpa
        # If Data is already datetime-like, avoid passing to converter_data_flexivel
        if pd.api.types.is_datetime64_any_dtype(df["Data"]) or isinstance(df.loc[0, "Data"], pd.Timestamp):
            df["Data"] = pd.to_datetime(df["Data"], errors="coerce").dt.normalize()
        else:
            df["Data"] = converter_data_flexivel(df["Data"], preservar_hora=False)
        df["Valor"] = converter_numero_flexivel(df["Valor"])
        df["Categoria"] = df["Categoria"].astype(str).str.strip()

        adicionar_linha_aba(spreadsheet, "DebitoAvulso", df)
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

        df = pd.DataFrame(
            [[_get_hoje(), desc, cat, valor, conta]],
            columns=SCHEMA_ABAS["Receitas"]
        )
        # Normalizações: Data date-only, Valor numeric, categoria limpa
        if pd.api.types.is_datetime64_any_dtype(df["Data"]) or isinstance(df.loc[0, "Data"], pd.Timestamp):
            df["Data"] = pd.to_datetime(df["Data"], errors="coerce").dt.normalize()
        else:
            df["Data"] = converter_data_flexivel(df["Data"], preservar_hora=False)
        df["Valor"] = converter_numero_flexivel(df["Valor"])
        df["Categoria"] = df["Categoria"].astype(str).str.strip()

        adicionar_linha_aba(spreadsheet, "Receitas", df)
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

        df = pd.DataFrame(
            [[_get_hoje(), desc, cat, cart, valor, parcelas]],
            columns=SCHEMA_ABAS["ComprasCartao"]
        )
        # Normalizações: Data date-only, ValorTotal numeric, Parcelas int, Cartao normalized
        if pd.api.types.is_datetime64_any_dtype(df["Data"]) or isinstance(df.loc[0, "Data"], pd.Timestamp):
            df["Data"] = pd.to_datetime(df["Data"], errors="coerce").dt.normalize()
        else:
            df["Data"] = converter_data_flexivel(df["Data"], preservar_hora=False)
        df["ValorTotal"] = converter_numero_flexivel(df["ValorTotal"])
        df["Parcelas"] = pd.to_numeric(df["Parcelas"], errors="coerce").fillna(0).astype(int)
        df["Cartao"] = df["Cartao"].astype(str).apply(normalizar_nome_cartao)

        logger.debug(f"Cartão - Schema esperado: {SCHEMA_ABAS['ComprasCartao']}")
        logger.debug(f"Cartão - DataFrame colunas: {df.columns.tolist()}")
        
        adicionar_linha_aba(spreadsheet, "ComprasCartao", df)
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

        df = pd.DataFrame(
            [[_get_hoje(), desc, cat, total, entrada, pagas]],
            columns=SCHEMA_ABAS["PixParcelado"]
        )
        # Normalizações: Data date-only, Valores numeric, QtdPagas int
        if pd.api.types.is_datetime64_any_dtype(df["Data"]) or isinstance(df.loc[0, "Data"], pd.Timestamp):
            df["Data"] = pd.to_datetime(df["Data"], errors="coerce").dt.normalize()
        else:
            df["Data"] = converter_data_flexivel(df["Data"], preservar_hora=False)
        df["ValorTotal"] = converter_numero_flexivel(df["ValorTotal"])
        df["ValorEntrada"] = converter_numero_flexivel(df["ValorEntrada"])
        df["QtdPagas"] = pd.to_numeric(df["QtdPagas"], errors="coerce").fillna(0).astype(int)
        df["Categoria"] = df["Categoria"].astype(str).str.strip()

        adicionar_linha_aba(spreadsheet, "PixParcelado", df)
        logger.info(f"Pix parcelado registrado: {desc} - R${total}")
        await update.message.reply_text(
            f"✅ Pix parcelado salvo: {desc}\nTotal: R${total}\nEntrada: R${entrada}\nParceladas: {pagas}"
        )
    except Exception as e:
        logger.error(f"Erro ao registrar Pix parcelado: {e}")
        await update.message.reply_text(
            f"Erro ao salvar Pix. Use: /pix <total> <descrição> <categoria> <entrada> <pagas>"
        )


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
        df = pd.DataFrame(
            [[pd.Timestamp.now(), tipo, oper, valor, qtd]],
            columns=SCHEMA_ABAS["Investimentos"]
        )
        # Normalizações: DataHora preserva hora (DateTime), Valor numeric, Quantidade numeric
        try:
            # If DataHora is already datetime-like, avoid passing to converter_data_flexivel
            if pd.api.types.is_datetime64_any_dtype(df["DataHora"]) or isinstance(df.loc[0, "DataHora"], pd.Timestamp):
                df["DataHora"] = pd.to_datetime(df["DataHora"], errors="coerce")
            else:
                df["DataHora"] = converter_data_flexivel(df["DataHora"], preservar_hora=True)

            df["Valor"] = converter_numero_flexivel(df["Valor"])
            df["QuantidadeCripto"] = pd.to_numeric(df["QuantidadeCripto"], errors="coerce").fillna(0.0)
            
            logger.debug(f"Investimento - Schema esperado: {SCHEMA_ABAS['Investimentos']}")
            logger.debug(f"Investimento - DataFrame colunas: {df.columns.tolist()}")
            logger.debug(f"Investimento - DataFrame valores: {df.values.tolist()}")
        except Exception as e:
            logger.exception("Erro ao normalizar dados de investimento: %s", e)
            await update.message.reply_text(
                f"Erro ao processar valores do investimento: {e}"
            )
            return
        adicionar_linha_aba(spreadsheet, "Investimentos", df)
        logger.info(f"Investimento registrado: {tipo} {oper} - R${valor}")
        await update.message.reply_text(
            f"✅ Investimento salvo: {tipo}\nOperação: {oper}\nValor: R${valor}\nQuantidade: {qtd}"
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