import os
import subprocess
from datetime import datetime
from functools import wraps

import pandas as pd
from telegram import Update
from telegram.constants import ParseMode
from telegram.error import TimedOut, NetworkError
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Importações da arquitetura de serviços
from services.google_sheets import conectar_google_sheets, adicionar_linha_aba
from services.database import adicionar_linha_db
from utils.logging_config import get_logger
from utils.data_utils import converter_numero_flexivel

from config import TELEGRAM_TOKEN, AUTHORIZED_USER_ID, SCHEMA_ABAS
from services.google_sheets import conectar_google_sheets, adicionar_linha_aba

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

# --- LÓGICA DE REGISTO ---
async def processar_e_salvar(update: Update, aba: str, dados: dict):
    """Executa a escrita em duplicado, garantindo a ordem correta das colunas."""
    try:
        df = pd.DataFrame([dados])
        
        # A MÁGICA ESTÁ AQUI: 
        # Reordena o DataFrame para bater exatamente com o que o Sheets espera
        if aba in SCHEMA_ABAS:
            colunas_corretas = SCHEMA_ABAS[aba]
            # Reorganiza as colunas na ordem do SCHEMA_ABAS
            df = df[colunas_corretas]
        
        adicionar_linha_aba(spreadsheet, aba, df)
        adicionar_linha_db(aba, df)
        
        valor_display = dados.get('Valor', dados.get('ValorTotal', 0))
        await update.message.reply_text(
            f"✅ <b>{aba}</b> atualizada!\n💰 Montante: R$ {valor_display}", 
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Falha ao processar transação em {aba}: {e}")
        # Aqui ele vai te mostrar o erro real se algo mais falhar
        await update.message.reply_text(f"❌ Erro ao comunicar com os serviços: {e}")
# ==========================================
#              COMANDOS DO BOT
# ==========================================

@restrito
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Sistema Financeiro Online. Use /help para comandos.")

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
        
        "🔄 <b>Edições e Status:</b>\n"
        "📅 <code>/fatura_update [cartao] [nova_data]</code>\n"
        "🔢 <code>/pix_update [id_compra] [qtd_pagas]</code>\n"
        "🔔 <code>/ass_toggle [nome_assinatura]</code>\n\n"
        
        "⭐ <b>Desejos:</b>\n"
        "🛒 <code>/wish_add [preco] [nome_com_underline] [categoria] [prioridade]</code>\n\n"
        
        "🛠️ <b>Sistema:</b>\n"
        "🖥️ /status - <i>Telemetria e Saúde da VM</i>\n"
        "⚙️ /run_script - <i>Forçar execução do pipeline (ETL)</i>"
    )
    await update.message.reply_text(guia, parse_mode=ParseMode.HTML)

@restrito
async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Monitorização em tempo real dos recursos do servidor."""
    try:
        ram = subprocess.check_output("free -m | awk 'NR==2{printf \"%.2f%%\", $3*100/$2 }'", shell=True).decode().strip()
        disco = subprocess.check_output("df -h / | awk '$NF==\"/\"{printf \"%s\", $5}'", shell=True).decode().strip()
        
        msg = (
            "🖥️ <b>Saúde do Servidor:</b>\n"
            f"• RAM em uso: {ram}\n"
            f"• Espaço em Disco: {disco}\n"
            "• Base de Dados: Conectada"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    except Exception:
        await update.message.reply_text("⚠️ Erro ao obter telemetria do sistema.")

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
    """Lida com investimentos em CDI, BTC ou Cripto."""
    if len(context.args) < 3:
        return await update.message.reply_text("⚠️ Formato: /invest [tipo] [op] [valor] [qtd_cripto]")
    
    # Validação da quantidade de cripto para evitar erros em CDI
    qtd = converter_numero_flexivel(context.args[3]) if len(context.args) > 3 else 0.0

    dados = {
        "DataHora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Tipo": context.args[0].upper(),
        "Operacao": context.args[1],
        "Valor": converter_numero_flexivel(context.args[2]),
        "QuantidadeCripto": qtd  # Chave corrigida conforme o Sheets
    }
    await processar_e_salvar(update, "Investimentos", dados)

@restrito
async def run_script_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Executando motor ETL... Aguarde.")
    res = subprocess.run(["python3", "main.py"], capture_output=True, text=True)
    if res.returncode == 0:
        await update.message.reply_text("✅ Pipeline concluída com sucesso!")
    else:
        await update.message.reply_text("❌ Falha na execução do script principal.")

# ==========================================
#        NOVOS COMANDOS DE ATUALIZAÇÃO
# ==========================================

@restrito
async def fatura_update_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Atualiza a data do último ciclo pago de um cartão."""
    if len(context.args) < 2:
        return await update.message.reply_text("⚠️ Formato: /fatura_update [Cartão] [Nova_Data (DD/MM/YYYY)]")
    
    cartao = context.args[0]
    nova_data = context.args[1]
    
    try:
        # NOTA: Você precisará criar esta função nos seus services (ex: services/database.py e google_sheets.py)
        # atualizar_registro_db("faturas_pagas", "cartao", cartao, {"ultimo_ciclo_pago": nova_data})
        # atualizar_registro_sheets(spreadsheet, "FaturasPagas", "cartao", cartao, "ultimo_ciclo_pago", nova_data)
        
        await update.message.reply_text(f"✅ Fatura do <b>{cartao}</b> atualizada para: {nova_data}", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Erro ao atualizar fatura: {e}")
        await update.message.reply_text("❌ Falha ao atualizar fatura no banco/sheets.")

@restrito
async def pix_update_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Atualiza a quantidade de parcelas pagas de um Pix Parcelado."""
    if len(context.args) < 2:
        return await update.message.reply_text("⚠️ Formato: /pix_update [ID_da_Compra] [Qtd_Pagas]")
    
    id_compra = context.args[0]
    nova_qtd = int(context.args[1])
    
    try:
        # atualizar_registro_db("pix_parcelado", "id", id_compra, {"qtd_pagas": nova_qtd})
        # atualizar_registro_sheets(spreadsheet, "PixParcelado", "id", id_compra, "qtd_pagas", nova_qtd)
        
        await update.message.reply_text(f"✅ Compra PIX #{id_compra} atualizada: <b>{nova_qtd} parcelas pagas</b>.", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Erro ao atualizar PIX: {e}")
        await update.message.reply_text("❌ Falha ao atualizar parcelas do PIX.")

# ==========================================
#        SUGESTÕES DE NOVAS FUNCIONALIDADES
# ==========================================

@restrito
async def wishlist_add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adiciona um item rápido na sua Wishlist."""
    # Exemplo: /wish_add 500 "Anker Q30" Eletrônicos High
    if len(context.args) < 4:
        return await update.message.reply_text("⚠️ Formato: /wish_add [preco] [\"nome\"] [categoria] [prioridade]")
    
    # É interessante usar regex ou um delimitador para o nome se tiver espaços, 
    # mas simplificando para o formato por argumentos:
    dados = {
        "nome": context.args[1].replace("_", " "), # Usando underline para espaços se não usar aspas
        "preco": converter_numero_flexivel(context.args[0]),
        "categoria": context.args[2],
        "prioridade": context.args[3],
        "link": "Link Adicionado via Bot",
        # O ID deve ser autoincremental no banco/sheets
    }
    await processar_e_salvar(update, "Wishlist", dados)

@restrito
async def ass_toggle_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inverte o status (Ativa/Inativa) de uma assinatura."""
    if len(context.args) < 1:
        return await update.message.reply_text("⚠️ Formato: /ass_toggle [Nome_Assinatura]")
    
    nome_assinatura = " ".join(context.args)
    
    try:
        # Lógica ideal: buscar o status atual no DB, inverter o booleano e fazer o Update.
        # status_atual = buscar_registro_db("assinaturas", "nome", nome_assinatura)['ativa']
        # novo_status = not status_atual
        # atualizar_registro_db(...)
        # atualizar_registro_sheets(...)
        
        await update.message.reply_text(f"🔄 Status da assinatura <b>{nome_assinatura}</b> alterado com sucesso!", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text("❌ Falha ao alterar status da assinatura.")


# ==========================================
#              STARTUP
# ==========================================

def main():
    global spreadsheet
    logger.info("A ligar ao ecossistema Google...")
    spreadsheet = conectar_google_sheets()

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Registo de Comandos
    handlers = [
        ("start", start_cmd), ("help", help_cmd), ("status", status_cmd),
        ("debito", debito_cmd), ("receita", receita_cmd), ("cartao", cartao_cmd),
        ("pix", pix_cmd), ("invest", invest_cmd), ("run_script", run_script_cmd)
    ]
    
    for cmd, handler in handlers:
        app.add_handler(CommandHandler(cmd, handler))

    logger.info("Bot financeiro em escuta!")
    app.run_polling()

if __name__ == "__main__":
    main()