"""Formularios nativos (discord.ui.Modal) para registro rapido de transacoes.

Abertos a partir dos botoes do painel. Campos de conjunto fixo (Cartao,
Categoria, Conta, Prioridade) sao menus suspensos (Label + Select), garantindo
valores canonicos sem digitacao livre. Cada modal defere a interacao como
efemera em on_submit para evitar timeout enquanto o backend grava os dados.
"""

from __future__ import annotations

from datetime import datetime

import discord

from utils.data_utils import converter_numero_flexivel

from ui.constants import (
    CARTOES,
    CATEGORIAS,
    CATEGORIAS_RECEITA,
    CATEGORIA_PADRAO,
    CATEGORIA_RECEITA_PADRAO,
    CONTAS,
    CONTA_PADRAO,
    COR_ASSINATURA,
    COR_CARTAO,
    COR_DEBITO,
    COR_PIX,
    COR_RECEITA,
)
from ui.storage import gravar_e_confirmar


def _hoje() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _agora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def dropdown(
    texto: str,
    opcoes: list[str],
    *,
    padrao: str | None = None,
    descricao: str | None = None,
) -> discord.ui.Label:
    """Cria um campo de menu suspenso (Label + Select) para uso dentro de um Modal."""
    options = [
        discord.SelectOption(label=o, value=o, default=(o == padrao)) for o in opcoes
    ]
    return discord.ui.Label(
        text=texto,
        description=descricao,
        component=discord.ui.Select(placeholder="Selecione...", options=options, required=True),
    )


def _sel(campo: discord.ui.Label, padrao: str) -> str:
    """Le o valor escolhido em um campo dropdown, com fallback para o padrao."""
    valores = campo.component.values
    return valores[0] if valores else padrao


class ReceitaModal(discord.ui.Modal, title="🟢 Nova Receita"):
    valor = discord.ui.TextInput(label="Valor", placeholder="Ex: 1500", required=True)
    conta = dropdown("Conta de destino", CONTAS, padrao=CONTA_PADRAO)
    categoria = dropdown("Categoria", CATEGORIAS_RECEITA, padrao=CATEGORIA_RECEITA_PADRAO)
    descricao = discord.ui.TextInput(label="Descrição", placeholder="Origem da receita", required=True)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        dados = {
            "Data": _hoje(),
            "Valor": converter_numero_flexivel(str(self.valor.value)),
            "ContaDestino": _sel(self.conta, CONTA_PADRAO),
            "Categoria": _sel(self.categoria, CATEGORIA_RECEITA_PADRAO),
            "Descricao": str(self.descricao.value),
        }
        await gravar_e_confirmar(
            interaction, "Receitas", dados, titulo="🟢 Receita registrada!", cor=COR_RECEITA
        )


class DebitoModal(discord.ui.Modal, title="🔴 Novo Débito"):
    valor = discord.ui.TextInput(label="Valor", placeholder="Ex: 15,50", required=True)
    conta = dropdown("Conta de saída", CONTAS, padrao=CONTA_PADRAO)
    categoria = dropdown("Categoria", CATEGORIAS)
    descricao = discord.ui.TextInput(label="Descrição", placeholder="O que comprou?", required=True)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        dados = {
            "Data": _hoje(),
            "Valor": converter_numero_flexivel(str(self.valor.value)),
            "ContaSaida": _sel(self.conta, CONTA_PADRAO),
            "Categoria": _sel(self.categoria, CATEGORIA_PADRAO),
            "Descricao": str(self.descricao.value),
        }
        await gravar_e_confirmar(
            interaction, "DebitoAvulso", dados, titulo="🔴 Débito registrado!", cor=COR_DEBITO
        )


class CartaoModal(discord.ui.Modal, title="💳 Compra no Cartão"):
    valor = discord.ui.TextInput(label="Valor total", placeholder="Ex: 299,90", required=True)
    cartao = dropdown("Cartão", CARTOES, padrao=CARTOES[0])
    parcelas = discord.ui.TextInput(label="Parcelas", placeholder="Ex: 1", default="1", required=True)
    categoria = dropdown("Categoria", CATEGORIAS)
    descricao = discord.ui.TextInput(label="Descrição", placeholder="O que comprou?", required=True)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            parcelas = max(1, int(str(self.parcelas.value).strip() or "1"))
        except ValueError:
            parcelas = 1
        dados = {
            "Data": _agora(),
            "ValorTotal": converter_numero_flexivel(str(self.valor.value)),
            "Cartao": _sel(self.cartao, CARTOES[0]),
            "Parcelas": parcelas,
            "Categoria": _sel(self.categoria, CATEGORIA_PADRAO),
            "Descricao": str(self.descricao.value),
        }
        await gravar_e_confirmar(
            interaction, "ComprasCartao", dados, titulo="💳 Compra registrada!", cor=COR_CARTAO
        )


class PixModal(discord.ui.Modal, title="🔁 PIX Parcelado"):
    valor = discord.ui.TextInput(label="Valor total", placeholder="Ex: 500", required=True)
    entrada = discord.ui.TextInput(label="Valor de entrada", placeholder="O que já pagou agora", default="0", required=False)
    pagas = discord.ui.TextInput(label="Parcelas já pagas", placeholder="Ex: 1", default="1", required=True)
    categoria = dropdown("Categoria", CATEGORIAS)
    descricao = discord.ui.TextInput(label="Descrição", placeholder="Detalhes", required=True)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            pagas = max(0, int(str(self.pagas.value).strip() or "1"))
        except ValueError:
            pagas = 1
        dados = {
            "Data": _hoje(),
            "ValorTotal": converter_numero_flexivel(str(self.valor.value)),
            "ValorEntrada": converter_numero_flexivel(str(self.entrada.value or "0")),
            "QtdPagas": pagas,
            "Categoria": _sel(self.categoria, CATEGORIA_PADRAO),
            "Descricao": str(self.descricao.value),
        }
        await gravar_e_confirmar(
            interaction, "PixParcelado", dados, titulo="🔁 PIX registrado!", cor=COR_PIX
        )


class WishlistModal(discord.ui.Modal, title="⭐ Nova Wishlist"):
    preco = discord.ui.TextInput(label="Preço", placeholder="Ex: 199,90", required=True)
    nome = discord.ui.TextInput(label="Nome", placeholder="O que você quer?", required=True)
    categoria = dropdown("Categoria", CATEGORIAS)
    prioridade = dropdown("Prioridade", ["Baixa", "Media", "Alta"], padrao="Media")

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        dados = {
            "Nome": str(self.nome.value).replace("_", " "),
            "Preço": converter_numero_flexivel(str(self.preco.value)),
            "Categoria": _sel(self.categoria, CATEGORIA_PADRAO),
            "Prioridade": _sel(self.prioridade, "Media"),
            "Link": "Adicionado via Bot",
        }
        await gravar_e_confirmar(
            interaction, "Wishlist", dados, titulo="⭐ Item na Wishlist!", cor=COR_PIX
        )


class InvestModal(discord.ui.Modal, title="📈 Novo Investimento"):
    tipo = discord.ui.TextInput(label="Tipo", placeholder="Ex: Renda Fixa, Cripto", required=True)
    operacao = discord.ui.TextInput(label="Operação", placeholder="Aporte ou Saque", required=True)
    valor = discord.ui.TextInput(label="Valor", placeholder="Ex: 1000", required=True)
    qtd_cripto = discord.ui.TextInput(label="Quantidade cripto", placeholder="Ex: 0.01", default="0", required=False)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        dados = {
            "DataHora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Tipo": str(self.tipo.value).upper(),
            "Operacao": str(self.operacao.value),
            "Valor": converter_numero_flexivel(str(self.valor.value)),
            "QuantidadeCripto": converter_numero_flexivel(str(self.qtd_cripto.value or "0")),
        }
        await gravar_e_confirmar(
            interaction, "Investimentos", dados, titulo="📈 Investimento registrado!", cor=COR_CARTAO
        )


class AssinaturaModal(discord.ui.Modal, title="🔔 Nova Assinatura"):
    """Cria uma assinatura recorrente. Ja nasce ativa, iniciando hoje e sem data de fim
    (o ETL projeta 3 meses adiante). Use o menu de edicao para pausar/encerrar depois."""

    nome = discord.ui.TextInput(label="Nome da assinatura", placeholder="Ex: Netflix", required=True)
    valor = discord.ui.TextInput(label="Valor mensal", placeholder="Ex: 39,90", required=True)
    dia_cobranca = discord.ui.TextInput(
        label="Dia da cobrança", placeholder="Dia do mês, ex: 15", required=True
    )
    categoria = dropdown("Categoria", CATEGORIAS, padrao="Assinaturas")
    cartao = dropdown("Cartão", CARTOES, padrao=CARTOES[0])

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            dia = min(31, max(1, int(str(self.dia_cobranca.value).strip() or "1")))
        except ValueError:
            dia = 1
        dados = {
            "Nome": str(self.nome.value).strip(),
            "Categoria": _sel(self.categoria, CATEGORIA_PADRAO),
            "Valor": converter_numero_flexivel(str(self.valor.value)),
            "DiaCobranca": dia,
            "Cartao": _sel(self.cartao, CARTOES[0]),
            "Ativa": "TRUE",
            "Inicio": _hoje(),
            "Fim": None,
        }
        await gravar_e_confirmar(
            interaction, "Assinaturas", dados, titulo="🔔 Assinatura criada!", cor=COR_ASSINATURA
        )


class FaturaDataModal(discord.ui.Modal, title="💳 Atualizar Fatura"):
    """Aberto apos escolher o cartao no Select de edicao de fatura."""

    nova_data = discord.ui.TextInput(
        label="Novo último ciclo pago",
        placeholder="Ex: 01/07/2026",
        required=True,
    )

    def __init__(self, cartao: str, on_confirm) -> None:
        super().__init__()
        self.cartao = cartao
        self._on_confirm = on_confirm

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self._on_confirm(interaction, self.cartao, str(self.nova_data.value))


class PixQtdModal(discord.ui.Modal, title="🔁 Atualizar Parcelas"):
    """Aberto apos escolher a compra PIX no Select de edicao."""

    nova_qtd = discord.ui.TextInput(
        label="Parcelas pagas até agora",
        placeholder="Ex: 3",
        required=True,
    )

    def __init__(self, id_compra: str, descricao: str, on_confirm) -> None:
        super().__init__()
        self.id_compra = id_compra
        self.descricao = descricao
        self._on_confirm = on_confirm

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            qtd = max(0, int(str(self.nova_qtd.value).strip()))
        except ValueError:
            await interaction.followup.send("❌ Quantidade inválida.", ephemeral=True)
            return
        await self._on_confirm(interaction, self.id_compra, qtd)
