"""Ponto de entrada do bot financeiro do Discord.

Responsavel apenas pela inicializacao, seguranca global e roteamento. Toda a
logica de interface (Views, Modals, Selects) vive no pacote `ui`.
"""

import os
import subprocess
import sys
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from config import DISCORD_AUTHORIZED_USER_ID, DISCORD_TOKEN
from services.ai_parser import interpretar_gasto_com_ia
from services.database import atualizar_registro_db, ler_tabela_db
from services.google_sheets import atualizar_registro_sheets, conectar_google_sheets
from ui.constants import (
    CARTOES,
    CATEGORIAS,
    CONTAS,
    COR_CARTAO,
    COR_DEBITO,
    COR_PIX,
    COR_RECEITA,
    PRIORIDADES,
)
from ui.storage import gravar_e_confirmar
from ui.views import FaturaEditView, PainelView, PixEditView, painel_embed
from utils.data_utils import converter_numero_flexivel
from utils.logging_config import get_logger

logger = get_logger(__name__)
spreadsheet = None

# ==========================================
#         SEGURANCA GLOBAL (TREE)
# ==========================================


class RestrictedTree(app_commands.CommandTree):
    """Trava global: apenas o usuario autorizado interage com qualquer comando."""

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user and interaction.user.id == DISCORD_AUTHORIZED_USER_ID:
            return True

        logger.warning("Acesso via UI bloqueado. ID: %s", getattr(interaction.user, "id", "?"))
        # Autocomplete nao aceita send_message; so respondemos a comandos de fato.
        if interaction.type is discord.InteractionType.application_command:
            try:
                await interaction.response.send_message(
                    "⛔ Acesso restrito. Este bot é privado.", ephemeral=True
                )
            except discord.InteractionResponded:
                pass
        return False


# ==========================================
#         CONFIGURACAO DO BOT
# ==========================================

intents = discord.Intents.default()
intents.message_content = True


class FinancialBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="/",
            intents=intents,
            help_command=None,
            tree_cls=RestrictedTree,
        )

    async def setup_hook(self):
        # Registra a View persistente para que os botoes do painel sobrevivam a reinicios.
        self.add_view(PainelView())
        await self.tree.sync()
        logger.info("UI sincronizada e painel persistente registrado.")


bot = FinancialBot()


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
):
    if isinstance(error, app_commands.CheckFailure):
        return  # A trava global ja respondeu ao usuario.
    logger.error("Erro no comando: %s", error)
    if not interaction.response.is_done():
        await interaction.response.send_message(
            "⚠️ Ocorreu um erro ao processar o comando.", ephemeral=True
        )


# ==========================================
#         EVENTOS DO SISTEMA
# ==========================================


@bot.event
async def on_ready():
    global spreadsheet
    logger.info("A ligar ao ecossistema Google...")
    spreadsheet = conectar_google_sheets()
    logger.info("Bot logado como %s!", bot.user)


# ==========================================
#         CHOICES (DROPDOWNS FIXOS)
# ==========================================


def _choices(opcoes):
    """Converte uma lista de valores canonicos em choices nativos do Discord."""
    return [app_commands.Choice(name=o, value=o) for o in opcoes]


CHOICES_CATEGORIA = _choices(CATEGORIAS)
CHOICES_CONTA = _choices(CONTAS)
CHOICES_CARTAO = _choices(CARTOES)
CHOICES_PRIORIDADE = _choices(PRIORIDADES)


# ==========================================
#         PAINEL PRINCIPAL
# ==========================================


@bot.tree.command(name="painel", description="Abre o painel financeiro interativo")
async def painel_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(embed=painel_embed(), view=PainelView())


# ==========================================
#         SLASH COMMANDS DIRETOS
# ==========================================


@bot.tree.command(name="receita", description="Registra uma entrada de dinheiro")
@app_commands.describe(valor="Ex: 1500", conta="Conta de destino", categoria="Categoria", descricao="Origem da receita")
@app_commands.choices(conta=CHOICES_CONTA, categoria=CHOICES_CATEGORIA)
async def receita_cmd(interaction, valor: str, conta: str, categoria: str, descricao: str):
    await interaction.response.defer(ephemeral=True, thinking=True)
    dados = {
        "Data": datetime.now().strftime("%Y-%m-%d"),
        "Valor": converter_numero_flexivel(valor),
        "ContaDestino": conta,
        "Categoria": categoria,
        "Descricao": descricao,
    }
    await gravar_e_confirmar(interaction, "Receitas", dados, titulo="🟢 Receita registrada!", cor=COR_RECEITA)


@bot.tree.command(name="debito", description="Registra um débito avulso")
@app_commands.describe(valor="Ex: 15,50", conta="Conta de saída", categoria="Categoria", descricao="O que comprou")
@app_commands.choices(conta=CHOICES_CONTA, categoria=CHOICES_CATEGORIA)
async def debito_cmd(interaction, valor: str, conta: str, categoria: str, descricao: str):
    await interaction.response.defer(ephemeral=True, thinking=True)
    dados = {
        "Data": datetime.now().strftime("%Y-%m-%d"),
        "Valor": converter_numero_flexivel(valor),
        "ContaSaida": conta,
        "Categoria": categoria,
        "Descricao": descricao,
    }
    await gravar_e_confirmar(interaction, "DebitoAvulso", dados, titulo="🔴 Débito registrado!", cor=COR_DEBITO)


@bot.tree.command(name="cartao", description="Registra uma compra no cartão de crédito")
@app_commands.describe(valor_total="Valor final", cartao="Qual cartão", parcelas="Quantas vezes", categoria="Categoria", descricao="O que comprou")
@app_commands.choices(cartao=CHOICES_CARTAO, categoria=CHOICES_CATEGORIA)
async def cartao_cmd(interaction, valor_total: str, cartao: str, parcelas: int, categoria: str, descricao: str):
    await interaction.response.defer(ephemeral=True, thinking=True)
    dados = {
        "Data": datetime.now().strftime("%Y-%m-%d"),
        "ValorTotal": converter_numero_flexivel(valor_total),
        "Cartao": cartao,
        "Parcelas": parcelas,
        "Categoria": categoria,
        "Descricao": descricao,
    }
    await gravar_e_confirmar(interaction, "ComprasCartao", dados, titulo="💳 Compra registrada!", cor=COR_CARTAO)


@bot.tree.command(name="pix", description="Registra uma compra via PIX Parcelado")
@app_commands.describe(valor_total="Valor final", entrada="O que já pagou agora", pagas="Nº parcelas já quitadas", categoria="Categoria", descricao="Detalhes")
@app_commands.choices(categoria=CHOICES_CATEGORIA)
async def pix_cmd(interaction, valor_total: str, entrada: str, pagas: int, categoria: str, descricao: str):
    await interaction.response.defer(ephemeral=True, thinking=True)
    dados = {
        "Data": datetime.now().strftime("%Y-%m-%d"),
        "ValorTotal": converter_numero_flexivel(valor_total),
        "ValorEntrada": converter_numero_flexivel(entrada),
        "QtdPagas": pagas,
        "Categoria": categoria,
        "Descricao": descricao,
    }
    await gravar_e_confirmar(interaction, "PixParcelado", dados, titulo="🔁 PIX registrado!", cor=COR_PIX)


@bot.tree.command(name="invest", description="Registra uma operação de investimento")
@app_commands.describe(tipo="Ex: Renda Fixa, Cripto", operacao="Aporte/Saque", valor="Montante", qtd_cripto="Se cripto, quantidade")
async def invest_cmd(interaction, tipo: str, operacao: str, valor: str, qtd_cripto: str = "0"):
    await interaction.response.defer(ephemeral=True, thinking=True)
    dados = {
        "DataHora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Tipo": tipo.upper(),
        "Operacao": operacao,
        "Valor": converter_numero_flexivel(valor),
        "QuantidadeCripto": converter_numero_flexivel(qtd_cripto),
    }
    await gravar_e_confirmar(interaction, "Investimentos", dados, titulo="📈 Investimento registrado!", cor=COR_CARTAO)


@bot.tree.command(name="wish_add", description="Adiciona um item na Wishlist")
@app_commands.describe(preco="Valor do item", nome="O que você quer", cat="Categoria", prioridade="Baixa, Media, Alta")
@app_commands.choices(cat=CHOICES_CATEGORIA, prioridade=CHOICES_PRIORIDADE)
async def wishlist_add_cmd(interaction, preco: str, nome: str, cat: str, prioridade: str):
    await interaction.response.defer(ephemeral=True, thinking=True)
    dados = {
        "Nome": nome.replace("_", " "),
        "Preço": converter_numero_flexivel(preco),
        "Categoria": cat,
        "Prioridade": prioridade,
        "Link": "Adicionado via Bot",
    }
    await gravar_e_confirmar(interaction, "Wishlist", dados, titulo="⭐ Item na Wishlist!", cor=COR_PIX)


# ==========================================
#         EDICOES COM MENUS SUSPENSOS
# ==========================================


async def _confirmar_fatura(interaction: discord.Interaction, cartao: str, nova_data: str):
    payload = {"ultimo_ciclo_pago": nova_data}
    atualizar_registro_db("FaturasPagas", "cartao", cartao, payload)
    if spreadsheet is not None:
        atualizar_registro_sheets(spreadsheet, "FaturasPagas", "cartao", cartao, payload)
    await interaction.followup.send(
        f"✅ Fatura **{cartao}** atualizada para: **{nova_data}**", ephemeral=True
    )


@bot.tree.command(name="fatura", description="Atualiza o último ciclo pago de um cartão")
async def fatura_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(
        "💳 Selecione o cartão para atualizar a fatura:",
        view=FaturaEditView(_confirmar_fatura),
        ephemeral=True,
    )


async def _confirmar_pix(interaction: discord.Interaction, id_compra: str, nova_qtd: int):
    payload = {"qtd_pagas": nova_qtd}
    atualizar_registro_db("PixParcelado", "id", id_compra, payload)
    if spreadsheet is not None:
        atualizar_registro_sheets(spreadsheet, "PixParcelado", "id", id_compra, payload)
    await interaction.followup.send(
        f"✅ Compra PIX #{id_compra} atualizada: **{nova_qtd} parcelas pagas**.", ephemeral=True
    )


@bot.tree.command(name="pix_editar", description="Atualiza quantas parcelas de um PIX foram pagas")
async def pix_editar_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)

    df = ler_tabela_db("PixParcelado")
    if df.empty:
        await interaction.followup.send("📭 Nenhuma compra PIX encontrada.", ephemeral=True)
        return

    compras = [
        {
            "id": row.get("id", idx),
            "descricao": str(row.get("descricao", "—")),
            "valor": row.get("valor_total", 0),
            "pagas": row.get("qtd_pagas", 0),
        }
        for idx, row in df.tail(25).iterrows()
    ]

    await interaction.followup.send(
        "🔁 Selecione a compra PIX para atualizar as parcelas pagas:",
        view=PixEditView(compras, _confirmar_pix),
        ephemeral=True,
    )


@bot.tree.command(name="ass_toggle", description="Alterna o status de uma assinatura")
async def ass_toggle_cmd(interaction: discord.Interaction, nome_assinatura: str):
    await interaction.response.defer(ephemeral=True, thinking=True)
    await interaction.followup.send(
        f"🔄 Comando recebido para assinatura: **{nome_assinatura}**", ephemeral=True
    )


# ==========================================
#         TELEMETRIA / ETL
# ==========================================


@bot.tree.command(name="status", description="Telemetria da VM e banco de dados")
async def status_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        ram = subprocess.check_output(
            "free -m | awk 'NR==2{printf \"%.2f%%\", $3*100/$2 }'", shell=True
        ).decode().strip()
        disco = subprocess.check_output(
            "df -h / | awk '$NF==\"/\"{printf \"%s\", $5}'", shell=True
        ).decode().strip()
        msg = f"🖥️ **Saúde do Servidor:**\n• RAM: {ram}\n• Disco: {disco}\n• DB: Conectada"
        await interaction.followup.send(msg, ephemeral=True)
    except Exception:
        await interaction.followup.send("⚠️ Erro ao obter telemetria.", ephemeral=True)


@bot.tree.command(name="run_script", description="Recalcular todo o Fluxo de Caixa via ETL")
async def run_script_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)

    projeto_root = os.path.dirname(os.path.abspath(__file__))
    main_script = os.path.join(projeto_root, "main.py")

    res = subprocess.run(
        [sys.executable, main_script],
        cwd=projeto_root,
        capture_output=True,
        text=True,
    )
    if res.returncode == 0:
        await interaction.followup.send("✅ Pipeline de Fluxo de Caixa concluída com sucesso!", ephemeral=True)
    else:
        logger.error("run_script falhou: %s", res.stderr.strip() or res.stdout.strip())
        detalhe_erro = (res.stderr or res.stdout or "Erro desconhecido").strip()
        await interaction.followup.send(
            f"❌ Falha na execução do script principal.\n```\n{detalhe_erro[:1500]}\n```", ephemeral=True
        )


# ==========================================
#         TEXTO LIVRE (IA PARSER)
# ==========================================


@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return
    if message.author.id != DISCORD_AUTHORIZED_USER_ID:
        return
    # Ignora comandos de barra e mensagens vazias (anexos puros).
    if not message.content or message.content.startswith("/"):
        return

    status_msg = await message.reply("🧠 Interpretando registro...")
    dados_ia = interpretar_gasto_com_ia(message.content)

    if not dados_ia:
        await status_msg.edit(content="❌ Não consegui entender os dados. Tente ser mais claro.")
        return

    tipo_transacao = dados_ia.get("tipo", "debito").lower()
    data_atual = datetime.now().strftime("%Y-%m-%d")

    if tipo_transacao == "invalido":
        await status_msg.edit(
            content="❌ Injeção bloqueada! Sou um bot financeiro, não converso sobre outros assuntos. 💸"
        )
        return

    if tipo_transacao == "credito":
        aba_destino = "ComprasCartao"
        dados_finais = {
            "Data": data_atual,
            "ValorTotal": dados_ia["valor"],
            "Cartao": dados_ia["conta_cartao"],
            "Parcelas": dados_ia.get("parcelas", 1),
            "Categoria": dados_ia["categoria"],
            "Descricao": dados_ia["descricao"],
        }
    elif tipo_transacao == "receita":
        aba_destino = "Receitas"
        dados_finais = {
            "Data": data_atual,
            "Valor": dados_ia["valor"],
            "ContaDestino": dados_ia["conta_cartao"],
            "Categoria": dados_ia["categoria"],
            "Descricao": dados_ia["descricao"],
        }
    elif tipo_transacao == "investimento":
        aba_destino = "Investimentos"
        dados_finais = {
            "DataHora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Tipo": dados_ia["tipo_investimento"].upper(),
            "Operacao": dados_ia["operacao"],
            "Valor": dados_ia["valor"],
            "QuantidadeCripto": dados_ia.get("quantidade_cripto", 0.0),
        }
    elif tipo_transacao == "pix":
        aba_destino = "PixParcelado"
        dados_finais = {
            "Data": data_atual,
            "ValorTotal": dados_ia["valor"],
            "ValorEntrada": dados_ia.get("valor_entrada", 0.0),
            "QtdPagas": dados_ia.get("qtd_pagas", 1),
            "Categoria": dados_ia["categoria"],
            "Descricao": dados_ia["descricao"],
        }
    elif tipo_transacao == "wishlist":
        aba_destino = "Wishlist"
        dados_finais = {
            "Nome": dados_ia["descricao"],
            "Preço": dados_ia["valor"],
            "Categoria": dados_ia["categoria"],
            "Prioridade": dados_ia.get("prioridade", "Media"),
            "Link": "Adicionado via Bot",
        }
    else:
        aba_destino = "DebitoAvulso"
        dados_finais = {
            "Data": data_atual,
            "Valor": dados_ia["valor"],
            "ContaSaida": dados_ia["conta_cartao"],
            "Categoria": dados_ia["categoria"],
            "Descricao": dados_ia["descricao"],
        }

    try:
        from ui.storage import salvar_transacao

        salvar_transacao(aba_destino, dados_finais)
        valor = dados_finais.get("Valor", dados_finais.get("ValorTotal", dados_finais.get("Preço", 0)))
        await status_msg.edit(content=f"✅ **{aba_destino}** atualizada! 💰 R$ {valor}")
    except Exception as e:
        logger.error("Falha ao processar transação IA em %s: %s", aba_destino, e)
        await status_msg.edit(content=f"❌ Erro ao comunicar com os serviços: {e}")


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
