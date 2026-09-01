"""Testes do roteamento de investimentos por Classe.

O ponto central: antes, qualquer Tipo diferente de BTC/CDI era enviado a
CoinGecko como se fosse um ticker de cripto. As chamadas de rede sao
substituidas por dubles para que os testes rodem offline.
"""

from __future__ import annotations

import pandas as pd
import pytest

from processors import patrimonio as mod
from processors.patrimonio import PatrimonioCalculator


@pytest.fixture
def sem_rede(monkeypatch):
    """Intercepta as duas fontes de cotacao e registra o que foi consultado."""
    chamadas = {"coingecko": [], "brapi": []}

    def fake_resolver(self, ticker):
        chamadas["coingecko"].append(str(ticker).upper())
        return {"ticker": ticker, "id": str(ticker).lower(), "nome": f"Moeda {ticker}"}

    def fake_precos(self, coin_ids):
        return {coin_id: 10.0 for coin_id in coin_ids}

    def fake_brapi(tickers):
        chamadas["brapi"].extend(tickers)
        return {t: {"preco": 100.0, "nome": f"Ativo {t}"} for t in tickers}

    monkeypatch.setattr(PatrimonioCalculator, "_resolver_ativo_cripto", fake_resolver)
    monkeypatch.setattr(PatrimonioCalculator, "_buscar_precos_atuais", fake_precos)
    monkeypatch.setattr(mod, "buscar_cotacoes", fake_brapi)
    monkeypatch.setattr(PatrimonioCalculator, "_calcular_cdi", lambda self: pd.DataFrame())
    return chamadas


def _df(linhas: list[dict]) -> pd.DataFrame:
    base = {
        "DataHora": pd.Timestamp("2026-01-10"),
        "Classe": "Cripto",
        "Tipo": "BTC",
        "Operacao": "Aporte",
        "Valor": 1000.0,
        "Quantidade": 1.0,
    }
    return pd.DataFrame([{**base, **linha} for linha in linhas])


def test_ticker_da_b3_nao_vai_para_a_coingecko(sem_rede):
    """Regressao: BOVA11 caia no catch-all de cripto e sumia em silencio."""
    calc = PatrimonioCalculator(
        _df([{"Classe": "ETF", "Tipo": "BOVA11", "Quantidade": 10.0}])
    )
    resultado = calc.processar_tudo()

    assert sem_rede["coingecko"] == []
    assert sem_rede["brapi"] == ["BOVA11"]
    assert resultado["cripto"].empty
    assert list(resultado["renda_variavel"]["Ticker"]) == ["BOVA11"]


def test_renda_variavel_calcula_valor_em_reais(sem_rede):
    calc = PatrimonioCalculator(
        _df([{"Classe": "Acao", "Tipo": "PETR4", "Quantidade": 25.0}])
    )
    linha = calc.processar_tudo()["renda_variavel"].iloc[0]

    assert linha["Classe"] == "Acao"
    assert linha["SaldoCotas"] == 25.0
    assert linha["PrecoCota"] == 100.0
    assert linha["ValorReais"] == 2500.0


def test_saque_reduz_a_posicao(sem_rede):
    calc = PatrimonioCalculator(
        _df(
            [
                {"Classe": "ETF", "Tipo": "IVVB11", "Operacao": "Aporte", "Quantidade": 30.0},
                {"Classe": "ETF", "Tipo": "IVVB11", "Operacao": "Saque", "Quantidade": 12.0},
            ]
        )
    )
    linha = calc.processar_tudo()["renda_variavel"].iloc[0]

    assert linha["SaldoCotas"] == 18.0


def test_etf_e_acao_ficam_em_linhas_separadas(sem_rede):
    calc = PatrimonioCalculator(
        _df(
            [
                {"Classe": "ETF", "Tipo": "BOVA11", "Quantidade": 5.0},
                {"Classe": "Acao", "Tipo": "VALE3", "Quantidade": 7.0},
            ]
        )
    )
    df = calc.processar_tudo()["renda_variavel"]

    assert dict(zip(df["Ticker"], df["Classe"])) == {"BOVA11": "ETF", "VALE3": "Acao"}


def test_cripto_continua_indo_para_a_coingecko(sem_rede):
    calc = PatrimonioCalculator(
        _df([{"Classe": "Cripto", "Tipo": "ETH", "Quantidade": 2.0}])
    )
    resultado = calc.processar_tudo()

    assert sem_rede["coingecko"] == ["ETH"]
    assert sem_rede["brapi"] == []
    assert list(resultado["cripto"]["Ticker"]) == ["ETH"]


def test_btc_nao_aparece_na_tabela_de_criptos(sem_rede):
    """BTC tem tabela propria; nao pode ser contado duas vezes."""
    calc = PatrimonioCalculator(_df([{"Classe": "Cripto", "Tipo": "BTC"}]))
    resultado = calc.processar_tudo()

    assert resultado["cripto"].empty
    assert not resultado["btc"].empty


@pytest.mark.parametrize(
    ("classe", "tipo", "esperado"),
    [
        (None, "CDI", "CDI"),
        ("", "BTC", "CRIPTO"),
        (float("nan"), "ETH", "CRIPTO"),
        ("etf", "BOVA11", "ETF"),
        ("Acao", "PETR4", "ACAO"),
    ],
)
def test_classe_ausente_cai_na_heuristica_antiga(classe, tipo, esperado):
    assert PatrimonioCalculator._inferir_classe(classe, tipo) == esperado


def test_linhas_sem_classe_continuam_sendo_processadas(sem_rede):
    """Linhas gravadas antes da migracao nao podem sumir do patrimonio."""
    df = _df([{"Tipo": "SOL", "Quantidade": 3.0}]).drop(columns=["Classe"])
    resultado = PatrimonioCalculator(df).processar_tudo()

    assert list(resultado["cripto"]["Ticker"]) == ["SOL"]


def test_coluna_legada_quantidade_cripto_ainda_e_lida(sem_rede):
    """Compatibilidade com o intervalo entre o deploy do codigo e o ALTER TABLE."""
    df = _df([{"Classe": "Cripto", "Tipo": "SOL", "Quantidade": 0.0}])
    df["QuantidadeCripto"] = 4.0

    resultado = PatrimonioCalculator(df).processar_tudo()

    assert resultado["cripto"].iloc[0]["SaldoCripto"] == 4.0


def test_sem_renda_variavel_a_tabela_sai_vazia(sem_rede):
    calc = PatrimonioCalculator(_df([{"Classe": "Cripto", "Tipo": "ETH"}]))

    assert calc.processar_tudo()["renda_variavel"].empty
    assert sem_rede["brapi"] == []
