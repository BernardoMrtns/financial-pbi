"""Ponte entre a UI e os servicos de backend (DB / Sheets).

Centraliza a montagem do DataFrame, a gravacao e a construcao dos embeds de
recibo, para que Modals, Selects e Slash Commands compartilhem a mesma logica.
"""

from __future__ import annotations

import discord
import pandas as pd

from config import SCHEMA_ABAS
from services.database import adicionar_linha_db
from utils.logging_config import get_logger

from ui.constants import COR_ERRO

logger = get_logger(__name__)


def salvar_transacao(aba: str, dados: dict) -> None:
    """Monta o DataFrame na ordem do schema e persiste no PostgreSQL.

    Levanta excecao em caso de falha (o chamador decide como reportar ao usuario).
    """
    df = pd.DataFrame([dados])

    if aba in SCHEMA_ABAS:
        df = df[SCHEMA_ABAS[aba]]

    adicionar_linha_db(aba, df)
    logger.info("Transacao registrada na aba %s", aba)


def _valor_principal(dados: dict) -> float:
    for chave in ("Valor", "ValorTotal", "Preço"):
        if chave in dados:
            try:
                return float(dados[chave])
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def recibo_embed(
    aba: str,
    dados: dict,
    *,
    titulo: str,
    cor: discord.Color,
) -> discord.Embed:
    """Constroi um embed de confirmacao ('recibo') limpo a partir dos dados gravados."""
    embed = discord.Embed(title=titulo, color=cor)
    embed.description = f"Registro adicionado em **{aba}** com sucesso."

    embed.add_field(
        name="💰 Valor",
        value=f"R$ {_valor_principal(dados):,.2f}",
        inline=True,
    )

    # Campos secundarios relevantes, exibidos apenas quando presentes.
    rotulos = {
        "Categoria": "🏷️ Categoria",
        "Descricao": "📝 Descrição",
        "Nome": "📝 Item",
        "ContaSaida": "🏦 Conta",
        "ContaDestino": "🏦 Conta",
        "Cartao": "💳 Cartão",
        "Parcelas": "🔢 Parcelas",
        "ValorEntrada": "💵 Entrada",
        "QtdPagas": "✅ Parcelas pagas",
        "Prioridade": "⭐ Prioridade",
        "Tipo": "📈 Tipo",
        "Operacao": "🔁 Operação",
        "DiaCobranca": "📅 Dia da cobrança",
        "Inicio": "▶️ Início",
    }
    for chave, rotulo in rotulos.items():
        if chave in dados and str(dados[chave]).strip() not in ("", "0", "0.0"):
            embed.add_field(name=rotulo, value=str(dados[chave]), inline=True)

    embed.set_footer(text="Painel Financeiro • registro efêmero")
    return embed


def erro_embed(erro: Exception) -> discord.Embed:
    """Embed padrao para falhas na comunicacao com os servicos de backend."""
    embed = discord.Embed(
        title="❌ Falha ao registrar",
        description="Nao foi possivel comunicar com os servicos de backend.",
        color=COR_ERRO,
    )
    embed.add_field(name="Detalhe", value=f"```{str(erro)[:900]}```", inline=False)
    return embed


async def gravar_e_confirmar(
    interaction: discord.Interaction,
    aba: str,
    dados: dict,
    *,
    titulo: str,
    cor: discord.Color,
) -> None:
    """Grava a transacao e envia o recibo efemero.

    Assume que `interaction.response` ja sofreu `defer(ephemeral=True)`.
    """
    try:
        salvar_transacao(aba, dados)
    except Exception as erro:  # noqa: BLE001 - queremos reportar qualquer falha ao usuario
        logger.error("Falha ao salvar em %s: %s", aba, erro)
        await interaction.followup.send(embed=erro_embed(erro), ephemeral=True)
        return

    await interaction.followup.send(
        embed=recibo_embed(aba, dados, titulo=titulo, cor=cor),
        ephemeral=True,
    )
