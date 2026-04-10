"""
Módulo para cálculo de patrimônio (CDI e Bitcoin)
"""
import pandas as pd
import requests
import datetime
from modules.utils import obter_cdi_historico, calcular_fator_cdi_periodo, converter_numero_flexivel


class PatrimonioCalculator:
    """
    Responsável por calcular a evolução do patrimônio em investimentos
    """

    def __init__(self, df_investimentos):
        self.df_inv = df_investimentos
        self.hoje = pd.Timestamp.today().normalize()
        self._cache_ativos_cripto = {}

    def processar_tudo(self):
        """
        Processa ambos os tipos de investimento e retorna resultados
        """
        print("🪙  Processando Patrimônio (CDI e Cripto)...")

        df_cdi = pd.DataFrame()
        df_btc = pd.DataFrame()
        df_cripto = pd.DataFrame()

        try:
            if not self.df_inv.empty:
                # Normalização inicial
                self.df_inv["Tipo"] = self.df_inv["Tipo"].astype(str).str.upper().str.strip()
                self.df_inv["Operacao"] = self.df_inv["Operacao"].astype(str).str.upper().str.strip()
                self.df_inv["Quantidade"] = converter_numero_flexivel(self.df_inv["Quantidade"])
                self.df_inv["QuantidadeBTC"] = converter_numero_flexivel(self.df_inv["QuantidadeBTC"])

                # Coluna canônica de quantidade para ativos cripto (com fallback legado para QuantidadeBTC)
                self.df_inv["QuantidadeCripto"] = self.df_inv["Quantidade"]
                mask_qtd_zerada = self.df_inv["QuantidadeCripto"] == 0
                self.df_inv.loc[mask_qtd_zerada, "QuantidadeCripto"] = self.df_inv.loc[mask_qtd_zerada, "QuantidadeBTC"]

                # Regra exclusiva de BTC: converte satoshis para BTC quando o valor é inteiro grande
                mask_btc = self.df_inv["Tipo"] == "BTC"
                for idx in self.df_inv[mask_btc].index:
                    qtd = self.df_inv.loc[idx, "QuantidadeCripto"]
                    if qtd >= 1_000_000 and qtd == int(qtd):
                        self.df_inv.loc[idx, "QuantidadeCripto"] = qtd / 1e8

                def definir_sinal(op):
                    if "SAQUE" in op or "VENDA" in op or "RESGATE" in op: 
                        return -1
                    return 1

                self.df_inv["Sinal"] = self.df_inv["Operacao"].apply(definir_sinal)
                self.df_inv["ValorLiquido"] = self.df_inv["Valor"] * self.df_inv["Sinal"]
                self.df_inv["QtdLiquida"] = self.df_inv["QuantidadeCripto"] * self.df_inv["Sinal"]

                df_cdi = self._calcular_cdi()
                df_btc = self._calcular_bitcoin_snapshot()
                df_cripto = self._calcular_criptos_snapshot()

        except Exception as e:
            print(f"⚠️ Erro ao processar investimentos: {e}")

        return {
            'cdi': df_cdi,
            'btc': df_btc,
            'cripto': df_cripto
        }

    def _calcular_cdi(self):
        """
        Calcula evolução do CDI usando a série diária do Bacen com precisão temporal.
        """
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
        linhas = []

        for _, row in df_movimentos_cdi.iterrows():
            timestamp_atual = row["DataHora"]

            if timestamp_anterior is not None:
                fator_intervalo = calcular_fator_cdi_periodo(
                    timestamp_anterior,
                    timestamp_atual,
                    df_historico_cdi
                )
                saldo_atual *= fator_intervalo

            saldo_atual += row["ValorLiquido"]
            linhas.append({
                "Data": timestamp_atual,
                "ValorCDI": saldo_atual,
            })
            timestamp_anterior = timestamp_atual

        if timestamp_anterior is not None:
            agora = pd.Timestamp.now()
            saldo_corrente = saldo_atual * calcular_fator_cdi_periodo(
                timestamp_anterior,
                agora,
                df_historico_cdi
            )
            linhas.append({
                "Data": agora,
                "ValorCDI": saldo_corrente,
            })

        return pd.DataFrame(linhas)

    def _resolver_ativo_cripto(self, ticker):
        """
        Resolve ticker para ID/nome da API de cripto.
        """
        ticker = str(ticker).upper().strip()
        if ticker in self._cache_ativos_cripto:
            return self._cache_ativos_cripto[ticker]

        try:
            resp = requests.get(
                "https://api.coingecko.com/api/v3/search",
                params={"query": ticker},
                timeout=10
            ).json()
            coins = resp.get("coins", [])

            if not coins:
                self._cache_ativos_cripto[ticker] = None
                return None

            candidatos = [c for c in coins if str(c.get("symbol", "")).upper() == ticker]
            if not candidatos:
                candidatos = coins

            def chave_rank(item):
                rank = item.get("market_cap_rank")
                return rank if isinstance(rank, int) and rank > 0 else 10**9

            melhor = sorted(candidatos, key=chave_rank)[0]
            ativo = {
                "ticker": ticker,
                "id": melhor.get("id"),
                "nome": melhor.get("name", ticker)
            }
            self._cache_ativos_cripto[ticker] = ativo
            return ativo
        except Exception as e:
            print(f"⚠️ Erro ao resolver ticker {ticker}: {e}")
            self._cache_ativos_cripto[ticker] = None
            return None

    def _buscar_precos_atuais(self, coin_ids):
        """
        Busca preços atuais em lote para múltiplos ativos.
        """
        if not coin_ids:
            return {}

        ids = ",".join(sorted(set(coin_ids)))
        try:
            r = requests.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": ids, "vs_currencies": "brl"},
                timeout=10
            ).json()
            return {coin_id: r.get(coin_id, {}).get("brl", 0) for coin_id in set(coin_ids)}
        except Exception as e:
            print(f"⚠️ Erro ao buscar preços atuais de cripto: {e}")
            return {}

    def _calcular_snapshot_ativo_cripto(self, df_ativo, coin_id, ticker, nome_ativo):
        """
        Calcula snapshot atual consolidado de um ativo cripto.
        """
        if df_ativo.empty:
            return pd.DataFrame()

        saldo_total = df_ativo["QtdLiquida"].sum()
        precos = self._buscar_precos_atuais([coin_id])
        preco_atual = precos.get(coin_id, 0)

        if preco_atual == 0:
            print(f"⚠️ Não foi possível obter preço atual de {ticker}")
            return pd.DataFrame()

        return pd.DataFrame([{
            "DataHora": pd.Timestamp.now(),
            "Ticker": ticker,
            "Ativo": nome_ativo,
            "SaldoCripto": saldo_total,
            "PrecoCripto": preco_atual,
            "ValorReais": saldo_total * preco_atual
        }])

    def _calcular_criptos_snapshot(self):
        """
        Calcula snapshot atual para todas as criptomoedas (exceto BTC).
        """
        tipo_normalizado = self.df_inv["Tipo"].astype(str).str.upper().str.strip()
        df_cripto = self.df_inv[
            (~tipo_normalizado.isin(["BTC", "CDI"])) & (tipo_normalizado != "")
        ].copy()

        if df_cripto.empty:
            return pd.DataFrame()

        ativos_resolvidos = {}
        for ticker in sorted(df_cripto["Tipo"].unique()):
            ativo = self._resolver_ativo_cripto(ticker)
            if ativo and ativo.get("id"):
                ativos_resolvidos[ticker] = ativo
            else:
                print(f"⚠️ Ticker não reconhecido para cripto: {ticker}")

        if not ativos_resolvidos:
            return pd.DataFrame()

        precos_atuais = self._buscar_precos_atuais([a["id"] for a in ativos_resolvidos.values()])
        linhas = []

        for ticker, ativo in ativos_resolvidos.items():
            saldo_total = df_cripto[df_cripto["Tipo"] == ticker]["QtdLiquida"].sum()
            preco_atual = precos_atuais.get(ativo["id"], 0)

            if preco_atual == 0:
                continue

            linhas.append({
                "DataHora": pd.Timestamp.now(),
                "Ticker": ticker,
                "Ativo": ativo["nome"],
                "SaldoCripto": saldo_total,
                "PrecoCripto": preco_atual,
                "ValorReais": saldo_total * preco_atual
            })

        return pd.DataFrame(linhas)

    def _calcular_bitcoin_snapshot(self):
        """
        Calcula snapshot atual do investimento em BTC
        Retorna uma única linha com saldo atual e preço atual
        """
        df_btc = self.df_inv[self.df_inv["Tipo"] == "BTC"].copy()

        if df_btc.empty:
            return pd.DataFrame()

        # Remove transações com data inválida e calcula saldo total
        df_btc = df_btc[df_btc["Data"].notna()]
        
        if df_btc.empty:
            print("  ⚠️ Nenhuma transação BTC com data válida")
            return pd.DataFrame()

        snapshot_btc = self._calcular_snapshot_ativo_cripto(
            df_btc,
            coin_id="bitcoin",
            ticker="BTC",
            nome_ativo="Bitcoin"
        )
        if snapshot_btc.empty:
            return pd.DataFrame()

        snapshot_btc = snapshot_btc.rename(
            columns={"SaldoCripto": "SaldoBTC", "PrecoCripto": "PrecoBTC"}
        )
        return snapshot_btc[["DataHora", "SaldoBTC", "PrecoBTC", "ValorReais"]]