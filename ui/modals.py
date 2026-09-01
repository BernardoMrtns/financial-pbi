"""Formularios nativos (discord.ui.Modal) para registro rapido de transacoes.

Abertos a partir dos botoes do painel. Campos de conjunto fixo (Cartao,
Categoria, Conta, Prioridade) sao menus suspensos (Label + Select), garantindo
valores canonicos sem digitacao livre. Cada modal defere a interacao como
efemera em on_submit para evitar timeout enquanto o backend grava os dados.
"""

from __future__ import annotations

from datetime import datetime

import discord

from utils.data_utils import converter_numero_flexivel, resolver_cobranca_assinatura

from ui.constants import (
    CARTOES,
    CATEGORIAS,
    CATEGORIAS_RECEITA,
    CATEGORIA_PADRAO,
    CATEGORIA_RECEITA_PADRAO,
    CLASSES_INVESTIMENTO,
    CLASSE_INVESTIMENTO_PADRAO,
    CONTAS,
    CONTA_PADRAO,
    COR_ASSINATURA,
    COR_CARTAO,
    COR_DEBITO,
    COR_PIX,
    COR_RECEITA,
    OPERACOES_INVESTIMENTO,
    OPERACAO_INVESTIMENTO_PADRAO,
    PERIODICIDADE_PADRAO,
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
    """A Classe define de onde vem a cotacao; Tipo e o ticker do ativo."""

    classe = dropdown(
        "Classe",
        CLASSES_INVESTIMENTO,
        padrao=CLASSE_INVESTIMENTO_PADRAO,
        descricao="CDI, Cripto, ETF ou Acao",
    )
    tipo = discord.ui.TextInput(label="Ticker", placeholder="Ex: CDI, BTC, BOVA11, PETR4", required=True)
    operacao = dropdown("Operação", OPERACOES_INVESTIMENTO, padrao=OPERACAO_INVESTIMENTO_PADRAO)
    valor = discord.ui.TextInput(label="Valor", placeholder="Ex: 1000", required=True)
    quantidade = discord.ui.TextInput(
        label="Quantidade",
        placeholder="Cotas, acoes ou cripto. Ex: 0.01",
        default="0",
        required=False,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        dados = {
            "DataHora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Classe": _sel(self.classe, CLASSE_INVESTIMENTO_PADRAO),
            "Tipo": str(self.tipo.value).upper(),
            "Operacao": _sel(self.operacao, OPERACAO_INVESTIMENTO_PADRAO),
            "Valor": converter_numero_flexivel(str(self.valor.value)),
            "Quantidade": converter_numero_flexivel(str(self.quantidade.value or "0")),
        }
        await gravar_e_confirmar(
            interaction, "Investimentos", dados, titulo="📈 Investimento registrado!", cor=COR_CARTAO
        )


def montar_assinatura(
    *,
    nome: str,
    valor: str,
    proxima_cobranca: str,
    categoria: str,
    cartao: str,
    periodicidade: str,
) -> tuple[dict, str | None]:
    """Monta a linha de Assinaturas a partir dos campos crus do formulario.

    Compartilhado pelo modal, pelo slash command e pelo Mini App do Telegram
    para que os tres produzam exatamente a mesma linha. Devolve (dados, aviso):
    o aviso e preenchido quando a data nao pode ser lida e caimos em hoje.
    """
    aviso = None
    cobranca = resolver_cobranca_assinatura(proxima_cobranca)

    if cobranca is None:
        hoje = datetime.now()
        inicio, dia = hoje.strftime("%Y-%m-%d"), hoje.day
        aviso = (
            f"⚠️ Não consegui ler `{proxima_cobranca}` como data (use DD/MM/AAAA). "
            f"Usei hoje ({hoje.strftime('%d/%m/%Y')}) como primeira cobrança."
        )
    else:
        inicio, dia = cobranca

    dados = {
        "Nome": str(nome).strip(),
        "Categoria": categoria,
        "Valor": converter_numero_flexivel(str(valor)),
        "Periodicidade": periodicidade,
        "DiaCobranca": dia,
        "Cartao": cartao,
        "Ativa": "TRUE",
        "Inicio": inicio,
        "Fim": None,
    }
    return dados, aviso


class AssinaturaModal(discord.ui.Modal, title="🔔 Nova Assinatura"):
    """Cria uma assinatura recorrente, ja ativa e sem data de fim.

    A periodicidade chega pronta do Select que abre este modal: o Discord limita
    modais a 5 componentes e os cinco campos abaixo ja ocupam o teto.
    """

    nome = discord.ui.TextInput(label="Nome da assinatura", placeholder="Ex: Netflix", required=True)
    valor = discord.ui.TextInput(label="Valor por cobrança", placeholder="Ex: 39,90", required=True)
    proxima_cobranca = discord.ui.TextInput(
        label="Próxima cobrança",
        placeholder="DD/MM/AAAA, ex: 10/03/2027",
        required=True,
    )
    categoria = dropdown("Categoria", CATEGORIAS, padrao="Assinaturas")
    cartao = dropdown("Cartão", CARTOES, padrao=CARTOES[0])

    def __init__(self, periodicidade: str = PERIODICIDADE_PADRAO) -> None:
        super().__init__()
        self.periodicidade = periodicidade
        self.title = f"🔔 Nova Assinatura ({periodicidade})"

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        dados, aviso = montar_assinatura(
            nome=str(self.nome.value),
            valor=str(self.valor.value),
            proxima_cobranca=str(self.proxima_cobranca.value),
            categoria=_sel(self.categoria, CATEGORIA_PADRAO),
            cartao=_sel(self.cartao, CARTOES[0]),
            periodicidade=self.periodicidade,
        )
        if aviso:
            await interaction.followup.send(aviso, ephemeral=True)
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
