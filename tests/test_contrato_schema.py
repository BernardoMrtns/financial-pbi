"""Garante que todas as superficies de escrita produzam as colunas do SCHEMA_ABAS.

Assinaturas e Investimentos sao gravadas por quatro caminhos independentes
(modal do Discord, slash command, Mini App do Telegram e parser de IA). Como
ui.storage.salvar_transacao faz `df[SCHEMA_ABAS[aba]]`, qualquer divergencia so
apareceria em producao, na hora de gravar.
"""

from __future__ import annotations

import json
import re

import pytest

from config import SCHEMA_ABAS

MINIAPP = "docs/index.html"


def test_assinatura_do_discord_bate_com_o_schema():
    from ui.modals import montar_assinatura

    dados, _ = montar_assinatura(
        nome="Netflix",
        valor="39,90",
        proxima_cobranca="15/10/2026",
        categoria="Assinaturas",
        cartao="Inter",
        periodicidade="Mensal",
    )
    assert sorted(dados) == sorted(SCHEMA_ABAS["Assinaturas"])


def test_assinatura_do_telegram_bate_com_o_schema():
    from bots.telegram_bot import _montar_assinatura

    dados, _ = _montar_assinatura(
        nome="Netflix",
        valor="39,90",
        proxima_cobranca="15/10/2026",
        categoria="Assinaturas",
        cartao="Inter",
        periodicidade="Anual",
    )
    assert sorted(dados) == sorted(SCHEMA_ABAS["Assinaturas"])


def test_as_duas_pontas_produzem_a_mesma_linha():
    from bots.telegram_bot import _montar_assinatura
    from ui.modals import montar_assinatura

    kwargs = dict(
        nome="Spotify",
        valor="21,90",
        proxima_cobranca="03/07/2027",
        categoria="Assinaturas",
        cartao="Nubank",
        periodicidade="Anual",
    )
    assert montar_assinatura(**kwargs)[0] == _montar_assinatura(**kwargs)[0]


def test_data_invalida_avisa_em_vez_de_gravar_1900():
    """Regressao: "5" (habito do campo antigo) virava serial de planilha."""
    from ui.modals import montar_assinatura

    dados, aviso = montar_assinatura(
        nome="X",
        valor="9",
        proxima_cobranca="5",
        categoria="Assinaturas",
        cartao="Inter",
        periodicidade="Mensal",
    )
    assert aviso is not None
    assert not dados["Inicio"].startswith("19")


@pytest.mark.parametrize("modal_cls", ["AssinaturaModal", "InvestModal"])
def test_modais_cabem_no_limite_do_discord(modal_cls):
    """Modais do Discord aceitam no maximo 5 componentes."""
    import ui.modals as modals

    cls = getattr(modals, modal_cls)
    instancia = cls() if modal_cls == "InvestModal" else cls("Mensal")
    assert len(instancia.children) <= 5


def test_investimento_do_discord_tem_classe_e_quantidade():
    import ui.modals as modals

    modal = modals.InvestModal()
    # Classe e Operacao sao dropdowns (discord.ui.Label), lidos via _sel.
    for campo in ("classe", "tipo", "operacao", "valor", "quantidade"):
        assert hasattr(modal, campo), campo


def test_miniapp_envia_as_mesmas_chaves_que_o_handler_espera():
    """As constantes canonicas do Mini App precisam espelhar ui/constants.py."""
    from ui.constants import CLASSES_INVESTIMENTO, PERIODICIDADES

    html = open(MINIAPP, encoding="utf-8").read()

    for lista, nome in ((PERIODICIDADES, "PERIODICIDADES"), (CLASSES_INVESTIMENTO, "CLASSES_INVESTIMENTO")):
        achado = re.search(rf"const {nome} = (\[[^\]]*\]);", html)
        assert achado, f"{nome} nao encontrada em {MINIAPP}"
        assert json.loads(achado.group(1)) == lista

    # Chaves do payload consumidas em bots/telegram_bot.py::on_webapp_data.
    for chave in ("proxima_cobranca:", "periodicidade:", "classe:", "qtd:"):
        assert chave in html, f"Mini App nao envia {chave}"


def test_parser_de_ia_declara_os_campos_de_investimento():
    import services.ai_parser as parser

    fonte = open(parser.__file__, encoding="utf-8").read()
    assert '"classe_investimento"' in fonte
    assert '"quantidade_cripto"' not in fonte
