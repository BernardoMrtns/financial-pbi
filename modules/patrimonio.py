"""
Módulo para cálculo de patrimônio (Porquinho CDI e Bitcoin)
"""
import pandas as pd
import requests
import datetime
from modules.utils import get_cdi_historico


class PatrimonioCalculator:
    """
    Responsável por calcular a evolução do patrimônio em investimentos
    """

    def __init__(self, df_investimentos):
        self.df_inv = df_investimentos
        self.hoje = pd.Timestamp.today().normalize()

    def processar_tudo(self):
        """
        Processa ambos os tipos de investimento e retorna resultados
        """
        print("🪙  Processando Patrimônio (CDI e Cripto)...")

        df_porquinho = pd.DataFrame()
        df_btc = pd.DataFrame()

        try:
            if not self.df_inv.empty:
                # Normalização inicial
                self.df_inv["Tipo"] = self.df_inv["Tipo"].astype(str).str.upper().str.strip()
                self.df_inv["Operacao"] = self.df_inv["Operacao"].astype(str).str.upper().str.strip()
                self.df_inv["QuantidadeBTC"] = pd.to_numeric(self.df_inv["QuantidadeBTC"], errors="coerce").fillna(0.0)

                def definir_sinal(op):
                    if "SAQUE" in op or "VENDA" in op or "RESGATE" in op: 
                        return -1
                    return 1

                self.df_inv["Sinal"] = self.df_inv["Operacao"].apply(definir_sinal)
                self.df_inv["ValorLiquido"] = self.df_inv["Valor"] * self.df_inv["Sinal"]
                self.df_inv["QtdLiquida"] = self.df_inv["QuantidadeBTC"] * self.df_inv["Sinal"]

                df_porquinho = self._calcular_porquinho_cdi()
                df_btc = self._calcular_bitcoin()

        except Exception as e:
            print(f"⚠️ Erro ao processar investimentos: {e}")

        return {
            'porquinho': df_porquinho,
            'btc': df_btc
        }

    def _calcular_porquinho_cdi(self):
        """
        Calcula evolução do Porquinho com correção CDI
        """
        df_pig = self.df_inv[self.df_inv["Tipo"] != "BTC"].copy()

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

    def _calcular_bitcoin(self):
        """
        Calcula evolução do investimento em BTC com cotação histórica
        """
        df_btc = self.df_inv[self.df_inv["Tipo"] == "BTC"].copy()

        if df_btc.empty:
            return pd.DataFrame()

        data_min = df_btc["Data"].min()
        ts_start = int(data_min.timestamp())
        ts_end = int(datetime.datetime.now().timestamp())
        url = f"https://api.coingecko.com/api/v3/coins/bitcoin/market_chart/range?vs_currency=brl&from={ts_start}&to={ts_end}"

        try:
            r = requests.get(url, timeout=15).json()
            if "prices" in r:
                df_precos = pd.DataFrame(r["prices"], columns=["Timestamp", "PrecoBTC"])
                df_precos["Data"] = pd.to_datetime(df_precos["Timestamp"], unit="ms").dt.normalize()
                df_precos = df_precos.drop_duplicates(subset=["Data"])

                fluxo_btc_dia = df_btc.groupby("Data")["QtdLiquida"].sum().reset_index()
                df_final_btc = pd.merge(df_precos, fluxo_btc_dia, on="Data", how="left")
                df_final_btc["QtdLiquida"] = df_final_btc["QtdLiquida"].fillna(0)
                df_final_btc["SaldoBTC"] = df_final_btc["QtdLiquida"].cumsum()
                df_final_btc["ValorReais"] = df_final_btc["SaldoBTC"] * df_final_btc["PrecoBTC"]

                return df_final_btc[["Data", "SaldoBTC", "PrecoBTC", "ValorReais"]]
        except Exception as e:
            print(f"Erro na API Coingecko: {e}")

        return pd.DataFrame()