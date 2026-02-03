import pandas as pd
import requests
from pandas.tseries.offsets import DateOffset
from config import DIA_FECHAMENTO_CARTAO


def converter_data_flexivel(series):
    """
    Converte datas em múltiplos formatos (Serial Date do Excel ou dd/mm/yyyy)
    """
    # 1. Primeiro, força tudo que não é número a virar NaN.
    # Isso evita o erro "ValueError: object is not compatible with origin"
    series_numeric = pd.to_numeric(series, errors='coerce')

    # 2. Converte os números válidos (Serial Date do Excel)
    dates_numeric = pd.to_datetime(series_numeric, unit='D', origin='1899-12-30', errors='coerce')

    # 3. Tenta converter o texto original (dd/mm/yyyy) para o que falhou no numérico
    dates_string = pd.to_datetime(series, dayfirst=True, errors='coerce')

    # 4. Combina: Usa a data numérica; se for NaT, usa a data de texto
    return dates_numeric.fillna(dates_string)


def calcular_mes_competencia(data_compra):
    """
    Calcula o mês de competência com base no dia de fechamento do cartão
    """
    if pd.isna(data_compra): 
        return pd.NaT
    if data_compra.day <= DIA_FECHAMENTO_CARTAO:
        return data_compra.to_period("M").to_timestamp()
    else:
        return (data_compra + DateOffset(months=1)).to_period("M").to_timestamp()


def get_cdi_historico(data_inicio):
    """
    Busca histórico de CDI na API do Banco Central
    """
    try:
        data_str = data_inicio.strftime("%d/%m/%Y")
        url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados?formato=json&dataInicial={data_str}"
        r = requests.get(url, timeout=10).json()
        df_cdi = pd.DataFrame(r)
        df_cdi["Data"] = pd.to_datetime(df_cdi["data"], format="%d/%m/%Y")
        df_cdi["Taxa"] = pd.to_numeric(df_cdi["valor"], errors="coerce")
        df_cdi["FatorDiario"] = 1 + (df_cdi["Taxa"] / 100)
        return df_cdi[["Data", "FatorDiario"]]
    except:
        return pd.DataFrame(columns=["Data", "FatorDiario"])