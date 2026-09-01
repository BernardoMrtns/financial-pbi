"""Testes da expansao de assinaturas em movimentacoes de fluxo de caixa.

Exercitam apenas processar_assinaturas(), sem banco nem rede: o processador
recebe DataFrames sinteticos e devolve a lista de Movimentacao ja montada.
"""

from __future__ import annotations

import pandas as pd
import pytest

from processors.fluxo_caixa import FluxoCaixaProcessor


def _processar(**campos) -> list:
    """Roda processar_assinaturas() para uma unica assinatura."""
    linha = {
        "Nome": "Teste",
        "Categoria": "Assinaturas",
        "Valor": 100.0,
        "Periodicidade": "Mensal",
        "DiaCobranca": None,
        "Cartao": "Inter",
        "Ativa": "TRUE",
        "Inicio": pd.Timestamp("2026-01-15"),
        "Fim": pd.NaT,
    }
    linha.update(campos)

    processor = FluxoCaixaProcessor(
        dados={"assinaturas": pd.DataFrame([linha])}, mapa_pagamentos={}
    )
    processor.processar_assinaturas()
    return processor.lista_movimentacoes


def _datas(movimentacoes) -> list[pd.Timestamp]:
    return sorted(m.data_original for m in movimentacoes)


def test_mensal_respeita_dia_de_cobranca():
    """Regressao: DiaCobranca era ignorado e tudo caia no dia do Inicio."""
    movs = _processar(
        Inicio=pd.Timestamp("2026-01-15"),
        DiaCobranca=5,
        Fim=pd.Timestamp("2026-04-30"),
    )

    dias = {d.day for d in _datas(movs)}
    assert dias == {5}


def test_mensal_nao_perde_o_primeiro_mes():
    """Regressao: freq='MS' ancorava no dia 1 e pulava o mes do Inicio."""
    movs = _processar(Inicio=pd.Timestamp("2026-01-15"), Fim=pd.Timestamp("2026-03-31"))

    datas = _datas(movs)
    assert datas[0] == pd.Timestamp("2026-01-15")
    assert [d.month for d in datas] == [1, 2, 3]


def test_anual_gera_uma_cobranca_no_mes_de_aniversario():
    movs = _processar(
        Periodicidade="Anual",
        Inicio=pd.Timestamp("2026-03-10"),
        Fim=pd.Timestamp("2027-01-31"),
    )

    datas = _datas(movs)
    assert datas == [pd.Timestamp("2026-03-10")]


def test_anual_sem_fim_cai_dentro_da_projecao():
    """Sem data de Fim, a janela de 13 meses garante exatamente uma cobranca."""
    hoje = pd.Timestamp.today().normalize()
    inicio = hoje + pd.DateOffset(months=6)

    movs = _processar(Periodicidade="Anual", Inicio=inicio, Fim=pd.NaT)

    datas = _datas(movs)
    assert len(datas) == 1
    assert datas[0].month == inicio.month
    assert datas[0].day == inicio.day


def test_anual_repete_a_cada_doze_meses():
    movs = _processar(
        Periodicidade="Anual",
        Inicio=pd.Timestamp("2024-03-10"),
        Fim=pd.Timestamp("2027-12-31"),
    )

    datas = _datas(movs)
    assert datas == [
        pd.Timestamp("2024-03-10"),
        pd.Timestamp("2025-03-10"),
        pd.Timestamp("2026-03-10"),
        pd.Timestamp("2027-03-10"),
    ]


def test_dia_31_recua_para_o_ultimo_dia_do_mes_curto():
    movs = _processar(
        Inicio=pd.Timestamp("2026-01-31"),
        DiaCobranca=31,
        Fim=pd.Timestamp("2026-03-31"),
    )

    datas = _datas(movs)
    assert pd.Timestamp("2026-02-28") in datas


@pytest.mark.parametrize("periodicidade", [None, "", "  ", "Trimestral"])
def test_periodicidade_ausente_ou_desconhecida_vira_mensal(periodicidade):
    """Compatibilidade com linhas gravadas antes da coluna existir."""
    movs = _processar(
        Periodicidade=periodicidade,
        Inicio=pd.Timestamp("2026-01-10"),
        Fim=pd.Timestamp("2026-04-30"),
    )

    assert [d.month for d in _datas(movs)] == [1, 2, 3, 4]


def test_descricao_distingue_anual_de_mensal():
    mensal = _processar(Fim=pd.Timestamp("2026-02-28"))
    anual = _processar(
        Periodicidade="Anual",
        Inicio=pd.Timestamp("2026-03-10"),
        Fim=pd.Timestamp("2026-12-31"),
    )

    assert mensal[0].descricao.endswith("(Assinatura)")
    assert anual[0].descricao.endswith("(Assinatura Anual)")
    # O Metodo alimenta a medida DAX TotalParcelasMes e nao pode variar.
    assert mensal[0].metodo == anual[0].metodo == "Assinatura Recorrente"


def test_assinatura_inativa_e_ignorada():
    assert _processar(Ativa="FALSE") == []


def test_fim_anterior_ao_inicio_e_ignorado():
    movs = _processar(
        Inicio=pd.Timestamp("2026-05-01"), Fim=pd.Timestamp("2026-01-01")
    )
    assert movs == []


def test_ultima_cobranca_nao_e_perdida_quando_o_dia_e_menor_que_o_do_inicio():
    """Inicio em 15/01 cobrando todo dia 5: a cobranca de 05/04 ainda vale."""
    movs = _processar(
        Inicio=pd.Timestamp("2026-01-15"),
        DiaCobranca=5,
        Fim=pd.Timestamp("2026-04-05"),
    )

    assert _datas(movs)[-1] == pd.Timestamp("2026-04-05")


def test_nao_gera_cobranca_depois_do_fim():
    movs = _processar(
        Inicio=pd.Timestamp("2026-01-10"),
        Fim=pd.Timestamp("2026-03-10"),
    )

    assert all(d <= pd.Timestamp("2026-03-10") for d in _datas(movs))
