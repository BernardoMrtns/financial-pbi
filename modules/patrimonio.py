"""
Módulo para cálculo de patrimônio (Porquinho CDI e Bitcoin)
"""
import pandas as pd
import requests
import datetime
from modules.utils import get_cdi_historico, converter_numero_flexivel


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

        df_porquinho = pd.DataFrame()
        df_btc = pd.DataFrame()
        df_btc_snapshot = pd.DataFrame()
        df_cripto = pd.DataFrame()
        df_cripto_snapshot = pd.DataFrame()

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

                df_porquinho = self._calcular_porquinho_cdi()
                df_btc = self._calcular_bitcoin()
                df_btc_snapshot = self._calcular_bitcoin_snapshot()
                df_cripto = self._calcular_criptos_historico()
                df_cripto_snapshot = self._calcular_criptos_snapshot()

        except Exception as e:
            print(f"⚠️ Erro ao processar investimentos: {e}")

        return {
            'porquinho': df_porquinho,
            'btc': df_btc,
            'btc_snapshot': df_btc_snapshot,
            'cripto': df_cripto,
            'cripto_snapshot': df_cripto_snapshot
        }

    def _calcular_porquinho_cdi(self):
        """
        Calcula evolução do Porquinho com correção CDI
        """
        df_pig = self.df_inv[self.df_inv["Tipo"] == "PORQUINHO"].copy()

        if df_pig.empty:
            return pd.DataFrame()

        data_min = df_pig["Data"].min()
        datas_full = pd.date_range(start=data_min, end=self.hoje, freq='D')
        df_cdi = get_cdi_historico(data_min)

        df_final_pig = pd.DataFrame(index=datas_full)
        df_final_pig.index.name = "Data"
        df_final_pig = df_final_pig.reset_index()

        fluxo_diario = df_pig.groupby("Data")["ValorLiquido"].sum().reset_index()
        df_final_pig = df_final_pig.merge(fluxo_diario, on="Data", how="left").fillna(0)
        df_final_pig = df_final_pig.merge(df_cdi, on="Data", how="left")
        df_final_pig["FatorDiario"] = df_final_pig["FatorDiario"].fillna(1.0)

        saldo_atual = 0
        saldos = []
        for _, row in df_final_pig.iterrows():
            saldo_atual = (saldo_atual * row["FatorDiario"]) + row["ValorLiquido"]
            saldos.append(saldo_atual)

        df_final_pig["ValorPorquinho"] = saldos
        return df_final_pig[["Data", "ValorPorquinho"]]

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

    def _buscar_precos_historicos(self, coin_id, ts_start, ts_end):
        """
        Busca série histórica de preços para um ativo cripto.
        """
        url = (
            f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart/range"
            f"?vs_currency=brl&from={ts_start}&to={ts_end}"
        )
        r = requests.get(url, timeout=15).json()
        prices = r.get("prices", [])
        if not prices:
            return pd.DataFrame()

        df_precos = pd.DataFrame(prices, columns=["Timestamp", "PrecoCripto"])
        df_precos["DataHora"] = pd.to_datetime(df_precos["Timestamp"], unit="ms")
        return df_precos[["DataHora", "PrecoCripto"]]

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

    def _calcular_historico_ativo_cripto(self, df_ativo, coin_id, ticker, nome_ativo):
        """
        Calcula histórico consolidado de um ativo cripto.
        """
        if df_ativo.empty:
            return pd.DataFrame()

        df_ativo = df_ativo[df_ativo["Data"].notna()].copy()
        if df_ativo.empty:
            return pd.DataFrame()

        ts_start = int(df_ativo["Data"].min().timestamp())
        ts_end = int(datetime.datetime.now().timestamp())
        df_precos = self._buscar_precos_historicos(coin_id, ts_start, ts_end)

        if df_precos.empty:
            print(f"⚠️ API Coingecko não retornou dados para {ticker}")
            return pd.DataFrame()

        resultado = []
        for _, row in df_ativo.iterrows():
            data_transacao = row["Data"]
            df_precos_temp = df_precos.copy()
            df_precos_temp["diff"] = (df_precos_temp["DataHora"] - data_transacao).abs()

            if df_precos_temp["diff"].empty:
                continue

            idx_mais_proximo = df_precos_temp["diff"].idxmin()
            preco_ativo = df_precos_temp.loc[idx_mais_proximo, "PrecoCripto"]

            resultado.append({
                "DataHora": data_transacao,
                "Ticker": ticker,
                "Ativo": nome_ativo,
                "QtdLiquida": row["QtdLiquida"],
                "PrecoCripto": preco_ativo
            })

        if not resultado:
            return pd.DataFrame()

        df_final = pd.DataFrame(resultado).sort_values("DataHora")
        df_final["SaldoCripto"] = df_final["QtdLiquida"].cumsum()
        df_final["ValorReais"] = df_final["SaldoCripto"] * df_final["PrecoCripto"]

        return df_final[["DataHora", "Ticker", "Ativo", "SaldoCripto", "PrecoCripto", "ValorReais"]]

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

    def _calcular_criptos_historico(self):
        """
        Calcula evolução histórica de criptomoedas (exceto BTC, que segue em fluxo dedicado).
        """
        df_cripto = self.df_inv[
            (~self.df_inv["Tipo"].isin(["PORQUINHO", "BTC"])) & (self.df_inv["Tipo"] != "")
        ].copy()

        if df_cripto.empty:
            return pd.DataFrame()

        resultados = []
        for ticker in sorted(df_cripto["Tipo"].unique()):
            ativo = self._resolver_ativo_cripto(ticker)
            if not ativo or not ativo.get("id"):
                print(f"⚠️ Ticker não reconhecido para cripto: {ticker}")
                continue

            df_ticker = df_cripto[df_cripto["Tipo"] == ticker].copy()
            hist = self._calcular_historico_ativo_cripto(
                df_ticker,
                coin_id=ativo["id"],
                ticker=ticker,
                nome_ativo=ativo["nome"]
            )
            if not hist.empty:
                resultados.append(hist)

        if not resultados:
            return pd.DataFrame()

        return pd.concat(resultados, ignore_index=True).sort_values(["DataHora", "Ticker"])

    def _calcular_criptos_snapshot(self):
        """
        Calcula snapshot atual para todas as criptomoedas (exceto BTC).
        """
        df_cripto = self.df_inv[
            (~self.df_inv["Tipo"].isin(["PORQUINHO", "BTC"])) & (self.df_inv["Tipo"] != "")
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

    def _calcular_bitcoin(self):
        """
        Calcula evolução do investimento em BTC com cotação histórica
        Mantém precisão de Date/Time nas transações
        """
        df_btc = self.df_inv[self.df_inv["Tipo"] == "BTC"].copy()

        if df_btc.empty:
            return pd.DataFrame()

        # Remove transações com data inválida
        df_btc = df_btc[df_btc["Data"].notna()]
        
        if df_btc.empty:
            print("⚠️ Nenhuma transação BTC com data válida")
            return pd.DataFrame()

        historico_btc = self._calcular_historico_ativo_cripto(
            df_btc,
            coin_id="bitcoin",
            ticker="BTC",
            nome_ativo="Bitcoin"
        )

        if historico_btc.empty:
            return pd.DataFrame()

        historico_btc = historico_btc.rename(
            columns={"SaldoCripto": "SaldoBTC", "PrecoCripto": "PrecoBTC"}
        )
        return historico_btc[["DataHora", "SaldoBTC", "PrecoBTC", "ValorReais"]]
    
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