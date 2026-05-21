import html
import os
import subprocess
import sys
from datetime import datetime
from functools import wraps

import pandas as pd
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

# Importações da arquitetura de serviços
from services.google_sheets import conectar_google_sheets, adicionar_linha_aba, atualizar_registro_sheets
from services.database import adicionar_linha_db, atualizar_registro_db
from services.ai_parser import interpretar_gasto_com_ia
from utils.logging_config import get_logger
from utils.data_utils import converter_numero_flexivel

from config import TELEGRAM_TOKEN, AUTHORIZED_USER_ID, SCHEMA_ABAS

logger = get_logger(__name__)

spreadsheet = None

# --- DECORADOR DE SEGURANÇA ---
def restrito(func):
    """Garante que apenas o administrador autorizado possa interagir com o bot."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.effective_user.id != AUTHORIZED_USER_ID:
            logger.warning(f"Acesso não autorizado bloqueado. ID: {update.effective_user.id}")
            await update.message.reply_text("⛔ Acesso restrito.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

# --- LÓGICA DE REGISTRO ---
async def processar_e_salvar(update: Update, aba: str, dados: dict):
    """Executa a escrita em duplicado, garantindo a ordem correta das colunas."""
    try:
        df = pd.DataFrame([dados])
        
        if aba in SCHEMA_ABAS:
            colunas_corretas = SCHEMA_ABAS[aba]
            df = df[colunas_corretas]
        
        adicionar_linha_aba(spreadsheet, aba, df)
        adicionar_linha_db(aba, df)
        
        valor_display = dados.get('Valor', dados.get('ValorTotal', dados.get('Preço', 0)))
        await update.message.reply_text(
            f"✅ <b>{aba}</b> atualizada!\n💰 Montante: R$ {valor_display}", 
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Falha ao processar transação em {aba}: {e}")
        await update.message.reply_text(f"❌ Erro ao comunicar com os serviços: {e}")

# ==========================================
#              SISTEMA E IA
# ==========================================

@restrito
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Sistema Financeiro Online ativo. Pode mandar os gastos por texto ou usar /help.")

@restrito
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    guia = (
        "🤖 <b>Centro de Comando Financeiro</b>\n"
        "<i>Toque em um comando para copiá-lo!</i>\n\n"
        
        "💰 <b>Registros Diários:</b>\n"
        "🔴 <code>/debito [valor] [conta] [categoria] [descrição]</code>\n"
        "🟢 <code>/receita [valor] [conta] [categoria] [descrição]</code>\n"
        "💳 <code>/cartao [total] [cartao] [parcelas] [categoria] [descrição]</code>\n"
        "🔁 <code>/pix [total] [entrada] [pagas] [categoria] [descrição]</code>\n"
        "📈 <code>/invest [tipo] [op] [valor] [qtd_cripto]</code>\n\n"
        
        "🔄 <b>Edições:</b>\n"
        "📅 <code>/fatura_update [cartao] [nova_data]</code>\n"
        "🔢 <code>/pix_update [id_compra] [qtd_pagas]</code>\n"
        "🔔 <code>/ass_toggle [nome_assinatura]</code>\n\n"
        
        "⭐ <b>Desejos:</b>\n"
        "🛒 <code>/wish_add [preco] [nome_com_underline] [cat] [prioridade]</code>\n\n"
        
        "🛠️ <b>Sistema:</b>\n"
        "🖥️ /status - <i>Telemetria da VM</i>\n"
        "⚙️ /run_script - <i>Recalcular Fluxo de Caixa</i>\n\n"
        "💡 <b>Dica:</b> Você pode apenas escrever <i>'15 no inter com lanche'</i> e a IA entende!"
    )
    await update.message.reply_text(guia, parse_mode=ParseMode.HTML)

@restrito
async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        ram = subprocess.check_output("free -m | awk 'NR==2{printf \"%.2f%%\", $3*100/$2 }'", shell=True).decode().strip()
        disco = subprocess.check_output("df -h / | awk '$NF==\"/\"{printf \"%s\", $5}'", shell=True).decode().strip()
        msg = f"🖥️ <b>Saúde do Servidor:</b>\n• RAM: {ram}\n• Disco: {disco}\n• DB: Conectada"
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    except Exception:
        await update.message.reply_text("⚠️ Erro ao obter telemetria.")

@restrito
async def mensagem_livre_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa texto natural usando IA e roteia para a aba correta."""
    status_msg = await update.message.reply_text("🧠 Interpretando registro...")
    
    dados_ia = interpretar_gasto_com_ia(update.message.text)
    
    if dados_ia:
        # 1. Tenta apagar a mensagem de status UMA ÚNICA VEZ com segurança
        try:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id, 
                message_id=status_msg.message_id
            )
        except Exception:
            pass
        
        tipo_transacao = dados_ia.get("tipo", "debito").lower()
        data_atual = datetime.now().strftime("%Y-%m-%d")

        # 2. Barreira de Fogo
        if tipo_transacao == "invalido":
            await update.message.reply_text("❌ Injeção bloqueada! Eu sou um bot financeiro, não converso sobre outros assuntos. 💸")
            return
        
        # 3. ROTEADOR DE ABAS E COLUNAS
        if tipo_transacao == "credito":
            dados_finais = {
                "Data": data_atual,
                "ValorTotal": dados_ia["valor"],
                "Cartao": dados_ia["conta_cartao"],
                "Parcelas": dados_ia.get("parcelas", 1),
                "Categoria": dados_ia["categoria"],
                "Descricao": dados_ia["descricao"]
            }
            aba_destino = "ComprasCartao"
            
        elif tipo_transacao == "receita":
            dados_finais = {
                "Data": data_atual,
                "Valor": dados_ia["valor"],
                "ContaDestino": dados_ia["conta_cartao"],
                "Categoria": dados_ia["categoria"],
                "Descricao": dados_ia["descricao"]
            }
            aba_destino = "Receitas"
            
        elif tipo_transacao == "investimento":
            dados_finais = {
                "DataHora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Tipo": dados_ia["tipo_investimento"].upper(),
                "Operacao": dados_ia["operacao"],
                "Valor": dados_ia["valor"],
                "QuantidadeCripto": dados_ia.get("quantidade_cripto", 0.0)
            }
            aba_destino = "Investimentos"
        
        elif tipo_transacao == "pix":
            dados_finais = {
                "Data": data_atual,
                "ValorTotal": dados_ia["valor"],
                "ValorEntrada": dados_ia.get("valor_entrada", 0.0),
                "QtdPagas": dados_ia.get("qtd_pagas", 1),
                "Categoria": dados_ia["categoria"],
                "Descricao": dados_ia["descricao"]
            }
            aba_destino = "PixParcelado"
            
        elif tipo_transacao == "wishlist":
            dados_finais = {
                "Nome": dados_ia["descricao"],
                "Preço": dados_ia["valor"],
                "Categoria": dados_ia["categoria"],
                "Prioridade": dados_ia.get("prioridade", "Mid"),
                "Link": "Adicionado via Bot"
            }
            aba_destino = "Wishlist"
            
        else: # Padrão: Débito Avulso
            dados_finais = {
                "Data": data_atual,
                "Valor": dados_ia["valor"],
                "ContaSaida": dados_ia["conta_cartao"],
                "Categoria": dados_ia["categoria"],
                "Descricao": dados_ia["descricao"]
            }
            aba_destino = "DebitoAvulso"

        await processar_e_salvar(update, aba_destino, dados_finais)
    else:
        await status_msg.edit_text("❌ Não consegui entender os dados. Tente ser mais claro.")        
# ==========================================
#         COMANDOS MANUAIS (BACKUP/GERAL)
# ==========================================

@restrito
async def debito_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 4:
        return await update.message.reply_text("⚠️ Formato: /debito [valor] [conta] [cat] [desc]")
    dados = {
        "Data": datetime.now().strftime("%Y-%m-%d"),
        "Valor": converter_numero_flexivel(context.args[0]),
        "ContaSaida": context.args[1],
        "Categoria": context.args[2],
        "Descricao": " ".join(context.args[3:])
    }
    await processar_e_salvar(update, "DebitoAvulso", dados)

@restrito
async def receita_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 4:
        return await update.message.reply_text("⚠️ Formato: /receita [valor] [conta] [cat] [desc]")
    dados = {
        "Data": datetime.now().strftime("%Y-%m-%d"),
        "Valor": converter_numero_flexivel(context.args[0]),
        "ContaDestino": context.args[1],
        "Categoria": context.args[2],
        "Descricao": " ".join(context.args[3:])
    }
    await processar_e_salvar(update, "Receitas", dados)

@restrito
async def cartao_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 5:
        return await update.message.reply_text("⚠️ Formato: /cartao [valor] [cartao] [parc] [cat] [desc]")
    dados = {
        "Data": datetime.now().strftime("%Y-%m-%d"),
        "ValorTotal": converter_numero_flexivel(context.args[0]),
        "Cartao": context.args[1],
        "Parcelas": int(context.args[2]),
        "Categoria": context.args[3],
        "Descricao": " ".join(context.args[4:])
    }
    await processar_e_salvar(update, "ComprasCartao", dados)

@restrito
async def pix_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 5:
        return await update.message.reply_text("⚠️ Formato: /pix [total] [ent] [pagas] [cat] [desc]")
    dados = {
        "Data": datetime.now().strftime("%Y-%m-%d"),
        "ValorTotal": converter_numero_flexivel(context.args[0]),
        "ValorEntrada": converter_numero_flexivel(context.args[1]),
        "QtdPagas": int(context.args[2]),
        "Categoria": context.args[3],
        "Descricao": " ".join(context.args[4:])
    }
    await processar_e_salvar(update, "PixParcelado", dados)

@restrito
async def invest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 3:
        return await update.message.reply_text("⚠️ Formato: /invest [tipo] [op] [valor] [qtd_cripto]")
    qtd = converter_numero_flexivel(context.args[3]) if len(context.args) > 3 else 0.0
    dados = {
        "DataHora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Tipo": context.args[0].upper(),
        "Operacao": context.args[1],
        "Valor": converter_numero_flexivel(context.args[2]),
        "QuantidadeCripto": qtd
    }
    await processar_e_salvar(update, "Investimentos", dados)

@restrito
async def run_script_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    projeto_root = os.path.dirname(os.path.abspath(__file__))
    main_script = os.path.join(projeto_root, "main.py")

    await update.message.reply_text("🔄 Executando motor ETL... Aguarde.")
    res = subprocess.run(
        [sys.executable, main_script],
        cwd=projeto_root,
        capture_output=True,
        text=True,
    )
    if res.returncode == 0:
        await update.message.reply_text("✅ Pipeline concluída com sucesso!")
    else:
        logger.error("run_script falhou: %s", res.stderr.strip() or res.stdout.strip())
        detalhe_erro = html.escape((res.stderr or res.stdout or "Erro desconhecido").strip())
        await update.message.reply_text(
            "❌ Falha na execução do script principal.\n"
            f"<pre>{detalhe_erro[:1500]}</pre>",
            parse_mode=ParseMode.HTML,
        )

# ==========================================
#         COMANDOS DE EDIÇÃO (UPDATE)
# ==========================================

@restrito
async def fatura_update_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        return await update.message.reply_text("⚠️ Use: /fatura_update [Cartão] [Nova_Data]")
    cartao, nova_data = context.args[0], context.args[1]
    payload = {"ultimo_ciclo_pago": nova_data}
    
    atualizar_registro_db("FaturasPagas", "cartao", cartao, payload)
    atualizar_registro_sheets(spreadsheet, "FaturasPagas", "cartao", cartao, payload)
    await update.message.reply_text(f"✅ Fatura <b>{cartao}</b> atualizada para: {nova_data}", parse_mode=ParseMode.HTML)

@restrito
async def pix_update_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        return await update.message.reply_text("⚠️ Use: /pix_update [ID_da_Compra] [Qtd_Pagas]")
    id_compra, nova_qtd = context.args[0], int(context.args[1])
    payload = {"qtd_pagas": nova_qtd}
    
    atualizar_registro_db("PixParcelado", "id", id_compra, payload)
    atualizar_registro_sheets(spreadsheet, "PixParcelado", "id", id_compra, payload)
    await update.message.reply_text(f"✅ Compra PIX #{id_compra} atualizada: <b>{nova_qtd} parcelas pagas</b>.", parse_mode=ParseMode.HTML)

@restrito
async def ass_toggle_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        return await update.message.reply_text("⚠️ Use: /ass_toggle [Nome_Assinatura]")
    
    # Exemplo simples, exigiria ler o status atual para inverter (toggle). 
    # Deixei o placeholder para você adicionar a lógica completa de busca, mas a função já não vai gerar erro no Pylance.
    nome_assinatura = " ".join(context.args)
    await update.message.reply_text(f"🔄 Comando recebido para assinatura: <b>{nome_assinatura}</b>", parse_mode=ParseMode.HTML)

@restrito
async def wishlist_add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 4:
        return await update.message.reply_text("⚠️ Formato: /wish_add [preco] [nome_underline] [cat] [prioridade]")
    dados = {
        "nome": context.args[1].replace("_", " "),
        "preco": converter_numero_flexivel(context.args[0]),
        "categoria": context.args[2],
        "prioridade": context.args[3],
        "link": "Adicionado via Bot"
    }
    await processar_e_salvar(update, "Wishlist", dados)


# ==========================================
#              STARTUP
# ==========================================

def main():
    global spreadsheet
    logger.info("A ligar ao ecossistema Google...")
    spreadsheet = conectar_google_sheets()

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Handlers Básicos
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("run_script", run_script_cmd))
    
    # Handlers de Lançamento Manual
    app.add_handler(CommandHandler("debito", debito_cmd))
    app.add_handler(CommandHandler("receita", receita_cmd))
    app.add_handler(CommandHandler("cartao", cartao_cmd))
    app.add_handler(CommandHandler("pix", pix_cmd))
    app.add_handler(CommandHandler("invest", invest_cmd))

    # Handlers de Atualização
    app.add_handler(CommandHandler("fatura_update", fatura_update_cmd))
    app.add_handler(CommandHandler("pix_update", pix_update_cmd))
    app.add_handler(CommandHandler("ass_toggle", ass_toggle_cmd))
    app.add_handler(CommandHandler("wish_add", wishlist_add_cmd))

    # Handler de texto livre (IA) SEMPRE POR ÚLTIMO
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), mensagem_livre_cmd))

    logger.info("Bot financeiro com IA em escuta!")
    app.run_polling()

if __name__ == "__main__":
    main()