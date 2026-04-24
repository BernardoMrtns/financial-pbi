from __future__ import annotations

from typing import Any

import pandas as pd
import requests
from requests import RequestException

from config import (
    COINGECKO_PRICE_URL,
    COINGECKO_SEARCH_URL,
    REQUEST_TIMEOUT_SECONDS,
    SATOSHIS_PER_BITCOIN,
)
from utils import (
    calcular_fator_cdi_periodo,
    converter_numero_flexivel,
    get_logger,
    obter_cdi_historico,
    retry_call,
)

logger = get_logger(__name__)


class PatrimonioCalculator:
    def __init__(self, df_investimentos: pd.DataFrame):
        self.df_inv = df_investimentos
        self.hoje = pd.Timestamp.today().normalize()
        self._cache_ativos_cripto: dict[str, dict[str, str] | None] = {}

    def processar_tudo(self) -> dict[str, pd.DataFrame]:
        logger.info("Processando patrimonio (CDI e Cripto)")

        df_cdi = pd.DataFrame()
        df_btc = pd.DataFrame()
        df_cripto = pd.DataFrame()

        try:
            if not self.df_inv.empty:
                self.df_inv["Tipo"] = self.df_inv["Tipo"].astype(str).str.upper().str.strip()
                self.df_inv["Operacao"] = self.df_inv["Operacao"].astype(str).str.upper().str.strip()
                self.df_inv["Quantidade"] = converter_numero_flexivel(self.df_inv["Quantidade"])
                self.df_inv["QuantidadeBTC"] = converter_numero_flexivel(self.df_inv["QuantidadeBTC"])

                self.df_inv["QuantidadeCripto"] = self.df_inv["Quantidade"]
                mask_qtd_zerada = self.df_inv["QuantidadeCripto"] == 0
                self.df_inv.loc[mask_qtd_zerada, "QuantidadeCripto"] = self.df_inv.loc[
                    mask_qtd_zerada, "QuantidadeBTC"
                ]

                mask_btc = self.df_inv["Tipo"] == "BTC"
                for idx in self.df_inv[mask_btc].index:
                    qtd = self.df_inv.loc[idx, "QuantidadeCripto"]
                    if qtd >= 1_000_000 and qtd == int(qtd):
                        self.df_inv.loc[idx, "QuantidadeCripto"] = qtd / SATOSHIS_PER_BITCOIN

                self.df_inv["Sinal"] = self.df_inv["Operacao"].apply(self._definir_sinal)
                self.df_inv["ValorLiquido"] = self.df_inv["Valor"] * self.df_inv["Sinal"]
                self.df_inv["QtdLiquida"] = self.df_inv["QuantidadeCripto"] * self.df_inv["Sinal"]

                df_cdi = self._calcular_cdi()
                df_btc = self._calcular_bitcoin_snapshot()
                df_cripto = self._calcular_criptos_snapshot()

        except Exception as error:
            logger.error("Erro ao processar investimentos: %s", error)

        return {"cdi": df_cdi, "btc": df_btc, "cripto": df_cripto}

    @staticmethod
    def _definir_sinal(operacao: str) -> int:
        if "SAQUE" in operacao or "VENDA" in operacao or "RESGATE" in operacao:
            return -1
        return 1

    def _calcular_cdi(self) -> pd.DataFrame:
        tipo_normalizado = self.df_inv["Tipo"].astype(str).str.upper().str.strip()
        df_movimentos_cdi = self.df_inv[tipo_normalizado.eq("CDI")].copy()

        if df_movimentos_cdi.empty:
            return pd.DataFrame()

        df_movimentos_cdi["DataHora"] = pd.to_datetime(df_movimentos_cdi["Data"], errors="coerce")
        df_movimentos_cdi = df_movimentos_cdi[df_movimentos_cdi["DataHora"].notna()].copy()

        if df_movimentos_cdi.empty:
            return pd.DataFrame()

        df_movimentos_cdi = df_movimentos_cdi.sort_values(["DataHora"], kind="mergesort").copy()
        data_min = df_movimentos_cdi["DataHora"].min().normalize()
        df_historico_cdi = obter_cdi_historico(data_min)

        saldo_atual = 0.0
        timestamp_anterior = None

        for row in df_movimentos_cdi.itertuples(index=False):
            timestamp_atual = row.DataHora
            if timestamp_anterior is not None:
                fator_intervalo = calcular_fator_cdi_periodo(timestamp_anterior, timestamp_atual, df_historico_cdi)
                saldo_atual *= fator_intervalo

            saldo_atual += row.ValorLiquido
            timestamp_anterior = timestamp_atual

        if timestamp_anterior is None:
            return pd.DataFrame()

        agora = pd.Timestamp.now()
        saldo_corrente = saldo_atual * calcular_fator_cdi_periodo(timestamp_anterior, agora, df_historico_cdi)

        snapshot_cdi = pd.DataFrame([
            {
                "DataHora": agora,
                "ValorCDI": saldo_corrente,
            }
        ])
        return snapshot_cdi[["DataHora", "ValorCDI"]]

    def _resolver_ativo_cripto(self, ticker: str) -> dict[str, str] | None:
        ticker = str(ticker).upper().strip()
        if ticker in self._cache_ativos_cripto:
            return self._cache_ativos_cripto[ticker]

        try:
            def fetch_search() -> dict[str, Any]:
                response = requests.get(
                    COINGECKO_SEARCH_URL,
                    params={"query": ticker},
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
                return response.json()

            resp = retry_call(fetch_search, (RequestException,), f"resolucao ticker {ticker}")
            coins = resp.get("coins", [])
            if not coins:
                self._cache_ativos_cripto[ticker] = None
                return None

            candidatos = [c for c in coins if str(c.get("symbol", "")).upper() == ticker]
            if not candidatos:
                candidatos = coins

            def chave_rank(item: dict[str, Any]) -> int:
                rank = item.get("market_cap_rank")
                return rank if isinstance(rank, int) and rank > 0 else 10**9

            melhor = sorted(candidatos, key=chave_rank)[0]
            ativo = {"ticker": ticker, "id": melhor.get("id", ""), "nome": melhor.get("name", ticker)}
            self._cache_ativos_cripto[ticker] = ativo
            return ativo
        except RuntimeError as error:
            logger.warning("Erro ao resolver ticker %s: %s", ticker, error)
            self._cache_ativos_cripto[ticker] = None
            return None

    def _buscar_precos_atuais(self, coin_ids: list[str]) -> dict[str, float]:
        if not coin_ids:
            return {}

        ids = ",".join(sorted(set(coin_ids)))
        try:
            def fetch_prices() -> dict[str, Any]:
                response = requests.get(
                    COINGECKO_PRICE_URL,
                    params={"ids": ids, "vs_currencies": "brl"},
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
                return response.json()

            payload = retry_call(fetch_prices, (RequestException,), "consulta de precos cripto")
            return {coin_id: payload.get(coin_id, {}).get("brl", 0.0) for coin_id in set(coin_ids)}
        except RuntimeError as error:
            logger.error("Erro ao buscar precos atuais de cripto: %s", error)
            return {}

    def _calcular_snapshot_ativo_cripto(
        self,
        df_ativo: pd.DataFrame,
        coin_id: str,
        ticker: str,
        nome_ativo: str,
    ) -> pd.DataFrame:
        if df_ativo.empty:
            return pd.DataFrame()

        saldo_total = df_ativo["QtdLiquida"].sum()
        precos = self._buscar_precos_atuais([coin_id])
        preco_atual = precos.get(coin_id, 0.0)

        if preco_atual == 0:
            logger.warning("Nao foi possivel obter preco atual de %s", ticker)
            return pd.DataFrame()

        return pd.DataFrame(
            [
                {
                    "DataHora": pd.Timestamp.now(),
                    "Ticker": ticker,
                    "Ativo": nome_ativo,
                    "SaldoCripto": saldo_total,
                    "PrecoCripto": preco_atual,
                    "ValorReais": saldo_total * preco_atual,
                }
            ]
        )

    def _calcular_criptos_snapshot(self) -> pd.DataFrame:
        tipo_normalizado = self.df_inv["Tipo"].astype(str).str.upper().str.strip()
        df_cripto = self.df_inv[(~tipo_normalizado.isin(["BTC", "CDI"])) & (tipo_normalizado != "")].copy()

        if df_cripto.empty:
            return pd.DataFrame()

        ativos_resolvidos: dict[str, dict[str, str]] = {}
        for ticker in sorted(df_cripto["Tipo"].unique()):
            ativo = self._resolver_ativo_cripto(ticker)
            if ativo and ativo.get("id"):
                ativos_resolvidos[ticker] = ativo
            else:
                logger.warning("Ticker nao reconhecido para cripto: %s", ticker)

        if not ativos_resolvidos:
            return pd.DataFrame()

        precos_atuais = self._buscar_precos_atuais([a["id"] for a in ativos_resolvidos.values() if a["id"]])
        linhas = []

        for ticker, ativo in ativos_resolvidos.items():
            saldo_total = df_cripto[df_cripto["Tipo"] == ticker]["QtdLiquida"].sum()
            preco_atual = precos_atuais.get(ativo["id"], 0.0)
            if preco_atual == 0:
                continue

            linhas.append(
                {
                    "DataHora": pd.Timestamp.now(),
                    "Ticker": ticker,
                    "Ativo": ativo["nome"],
                    "SaldoCripto": saldo_total,
                    "PrecoCripto": preco_atual,
                    "ValorReais": saldo_total * preco_atual,
                }
            )

        return pd.DataFrame(linhas)

    def _calcular_bitcoin_snapshot(self) -> pd.DataFrame:
        df_btc = self.df_inv[self.df_inv["Tipo"] == "BTC"].copy()
        if df_btc.empty:
            return pd.DataFrame()

        df_btc = df_btc[df_btc["Data"].notna()]
        if df_btc.empty:
            logger.warning("Nenhuma transacao BTC com data valida")
            return pd.DataFrame()

        snapshot_btc = self._calcular_snapshot_ativo_cripto(
            df_btc, coin_id="bitcoin", ticker="BTC", nome_ativo="Bitcoin"
        )
        if snapshot_btc.empty:
            return pd.DataFrame()

        snapshot_btc = snapshot_btc.rename(columns={"SaldoCripto": "SaldoBTC", "PrecoCripto": "PrecoBTC"})
        return snapshot_btc[["DataHora", "SaldoBTC", "PrecoBTC", "ValorReais"]]
