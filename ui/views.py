"""Views interativas: painel persistente e menus suspensos de edicao.

- PainelView e persistente (timeout=None + custom_id em cada botao), por isso
  continua funcional mesmo apos o bot reiniciar (registrada em setup_hook).
- Views de edicao usam discord.ui.Select para escolher cartao/transacao sem
  digitar IDs manualmente.
"""

from __future__ import annotations

from typing import Awaitable, Callable

import discord

from config import DISCORD_AUTHORIZED_USER_ID
from utils.logging_config import get_logger

from ui.constants import CARTOES, COR_PAINEL
from ui.modals import (
    CartaoModal,
    DebitoModal,
    FaturaDataModal,
    PixModal,
    PixQtdModal,
    ReceitaModal,
)

logger = get_logger(__name__)


class AuthorizedView(discord.ui.View):
    """Base que barra qualquer usuario diferente do autorizado nos componentes."""

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != DISCORD_AUTHORIZED_USER_ID:
            logger.warning("Acesso a componente bloqueado. ID: %s", interaction.user.id)
            await interaction.response.send_message(
                "⛔ Acesso restrito. Este bot é privado.", ephemeral=True
            )
            return False
        return True


class PainelView(AuthorizedView):
    """Painel principal persistente com botoes de registro rapido."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Receita", emoji="🟢", style=discord.ButtonStyle.success, custom_id="painel:receita"
    )
    async def receita(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(ReceitaModal())

    @discord.ui.button(
        label="Débito", emoji="🔴", style=discord.ButtonStyle.danger, custom_id="painel:debito"
    )
    async def debito(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(DebitoModal())

    @discord.ui.button(
        label="Cartão", emoji="💳", style=discord.ButtonStyle.primary, custom_id="painel:cartao"
    )
    async def cartao(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(CartaoModal())

    @discord.ui.button(
        label="PIX", emoji="🔁", style=discord.ButtonStyle.secondary, custom_id="painel:pix"
    )
    async def pix(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(PixModal())


def painel_embed() -> discord.Embed:
    """Embed limpo que acompanha o painel principal."""
    embed = discord.Embed(
        title="💠 Painel Financeiro",
        description=(
            "Registre movimentações em um clique. Use os botões abaixo para abrir "
            "o formulário correspondente.\n\n"
            "🟢 **Receita** · dinheiro entrando\n"
            "🔴 **Débito** · gasto avulso\n"
            "💳 **Cartão** · compra no crédito\n"
            "🔁 **PIX** · compra parcelada\n\n"
            "*Ou simplesmente digite naturalmente (ex: \"gastei 30 no ifood\") "
            "que a IA interpreta.*"
        ),
        color=COR_PAINEL,
    )
    embed.set_footer(text="Painel Financeiro • sempre ativo")
    return embed


# --- Callback assinaturas para as views de edicao ---
FaturaConfirm = Callable[[discord.Interaction, str, str], Awaitable[None]]
PixConfirm = Callable[[discord.Interaction, str, int], Awaitable[None]]


class _FaturaSelect(discord.ui.Select):
    def __init__(self, on_confirm: FaturaConfirm) -> None:
        options = [discord.SelectOption(label=c, emoji="💳") for c in CARTOES]
        super().__init__(placeholder="Escolha o cartão...", min_values=1, max_values=1, options=options)
        self._on_confirm = on_confirm

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(
            FaturaDataModal(self.values[0], self._on_confirm)
        )


class FaturaEditView(AuthorizedView):
    """Menu suspenso para escolher o cartao cuja fatura sera atualizada."""

    def __init__(self, on_confirm: FaturaConfirm) -> None:
        super().__init__(timeout=180)
        self.add_item(_FaturaSelect(on_confirm))


class _PixSelect(discord.ui.Select):
    def __init__(self, compras: list[dict], on_confirm: PixConfirm) -> None:
        self._mapa = {str(c["id"]): c for c in compras}
        self._on_confirm = on_confirm
        options = [
            discord.SelectOption(
                label=f"#{c['id']} · {c['descricao']}"[:100],
                description=f"Total R$ {c['valor']} · {c['pagas']} pagas"[:100],
                value=str(c["id"]),
            )
            for c in compras[:25]
        ]
        super().__init__(placeholder="Escolha a compra PIX...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        compra = self._mapa[self.values[0]]
        await interaction.response.send_modal(
            PixQtdModal(self.values[0], compra["descricao"], self._on_confirm)
        )


class PixEditView(AuthorizedView):
    """Menu suspenso listando compras PIX reais para atualizar as parcelas pagas."""

    def __init__(self, compras: list[dict], on_confirm: PixConfirm) -> None:
        super().__init__(timeout=180)
        self.add_item(_PixSelect(compras, on_confirm))
