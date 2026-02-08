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

    def processar_tudo(self):
        """
        Processa ambos os tipos de investimento e retorna resultados
        """
        print("🪙  Processando Patrimônio (CDI e Cripto)...")

        df_porquinho = pd.DataFrame()
        df_btc = pd.DataFrame()
        df_btc_snapshot = pd.DataFrame()

        try:
            if not self.df_inv.empty:
                # Normalização inicial
                self.df_inv["Tipo"] = self.df_inv["Tipo"].astype(str).str.upper().str.strip()
                self.df_inv["Operacao"] = self.df_inv["Operacao"].astype(str).str.upper().str.strip()
                self.df_inv["QuantidadeBTC"] = converter_numero_flexivel(self.df_inv["QuantidadeBTC"])

                # Detecta e converte satoshis para BTC por linha individual
                # Regra: se é inteiro (sem decimais) e > 0, é satoshi
                for idx in self.df_inv.index:
                    qtd = self.df_inv.loc[idx, "QuantidadeBTC"]
                    if qtd > 0 and qtd == int(qtd):  # É inteiro positivo = satoshi
                        self.df_inv.loc[idx, "QuantidadeBTC"] = qtd / 1e8

                def definir_sinal(op):
                    if "SAQUE" in op or "VENDA" in op or "RESGATE" in op: 
                        return -1
                    return 1

                self.df_inv["Sinal"] = self.df_inv["Operacao"].apply(definir_sinal)
                self.df_inv["ValorLiquido"] = self.df_inv["Valor"] * self.df_inv["Sinal"]
                self.df_inv["QtdLiquida"] = self.df_inv["QuantidadeBTC"] * self.df_inv["Sinal"]

                df_porquinho = self._calcular_porquinho_cdi()
                df_btc = self._calcular_bitcoin()
                df_btc_snapshot = self._calcular_bitcoin_snapshot()

        except Exception as e:
            print(f"⚠️ Erro ao processar investimentos: {e}")

        return {
            'porquinho': df_porquinho,
            'btc': df_btc,
            'btc_snapshot': df_btc_snapshot
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
        
        data_min = df_btc["Data"].min()
        ts_start = int(data_min.timestamp())
        ts_end = int(datetime.datetime.now().timestamp())
        url = f"https://api.coingecko.com/api/v3/coins/bitcoin/market_chart/range?vs_currency=brl&from={ts_start}&to={ts_end}"

        try:
            r = requests.get(url, timeout=15).json()
            
            if "prices" in r and len(r["prices"]) > 0:
                df_precos = pd.DataFrame(r["prices"], columns=["Timestamp", "PrecoBTC"])
                # Mantém datetime completo com hora para maior precisão
                df_precos["DataHora"] = pd.to_datetime(df_precos["Timestamp"], unit="ms")
                
                if df_precos.empty:
                    print("⚠️ API Coingecko retornou dados vazios para BTC")
                    return pd.DataFrame()
                
                # Para cada transação BTC, encontra o preço mais próximo
                resultado = []
                for idx, row in df_btc.iterrows():
                    data_transacao = row["Data"]
                    # Encontra o preço na API mais próximo do horário da transação
                    df_precos_temp = df_precos.copy()
                    df_precos_temp["diff"] = (df_precos_temp["DataHora"] - data_transacao).abs()
                    
                    if df_precos_temp["diff"].empty:
                        print(f"⚠️ Sem dados de preço para a transação em {data_transacao}")
                        continue
                    
                    idx_mais_proximo = df_precos_temp["diff"].idxmin()
                    preco_btc = df_precos_temp.loc[idx_mais_proximo, "PrecoBTC"]
                    
                    resultado.append({
                        "DataHora": data_transacao,
                        "QtdLiquida": row["QtdLiquida"],
                        "PrecoBTC": preco_btc
                    })
                
                if not resultado:
                    print("⚠️ Nenhuma transação BTC pôde ser processada")
                    return pd.DataFrame()
                
                df_final_btc = pd.DataFrame(resultado)
                df_final_btc = df_final_btc.sort_values("DataHora")
                df_final_btc["SaldoBTC"] = df_final_btc["QtdLiquida"].cumsum()
                df_final_btc["ValorReais"] = df_final_btc["SaldoBTC"] * df_final_btc["PrecoBTC"]

                return df_final_btc[["DataHora", "SaldoBTC", "PrecoBTC", "ValorReais"]]
            else:
                print("⚠️ API Coingecko não retornou dados de preços para BTC")
        except Exception as e:
            print(f"⚠️ Erro na API Coingecko: {e}")

        return pd.DataFrame()
    
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
        
        # Calcula saldo total de BTC
        saldo_btc_total = df_btc["QtdLiquida"].sum()
        
        # Busca preço atual do BTC
        try:
            url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=brl"
            r = requests.get(url, timeout=10).json()
            preco_btc_atual = r.get("bitcoin", {}).get("brl", 0)
            
            if preco_btc_atual == 0:
                print("⚠️ Não foi possível obter preço atual do BTC")
                return pd.DataFrame()
            
            # Cria snapshot com data/hora atual
            snapshot = pd.DataFrame([{
                "DataHora": pd.Timestamp.now(),
                "SaldoBTC": saldo_btc_total,
                "PrecoBTC": preco_btc_atual,
                "ValorReais": saldo_btc_total * preco_btc_atual
            }])
            
            return snapshot
            
        except Exception as e:
            print(f"⚠️ Erro ao buscar preço atual do BTC: {e}")
            return pd.DataFrame()