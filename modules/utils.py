import pandas as pd
import requests
from pandas.tseries.offsets import DateOffset
from config import FECHAMENTO_CARTOES


def converter_data_flexivel(series, preservar_hora=False):
    """
    Converte datas em múltiplos formatos (Serial Date do Excel, dd/mm/yyyy ou dd/mm/yyyy hh:mm:ss)
    Otimizado e vetorizado para alta performance.
    """
    s = series.copy().astype(object)
    s = s.replace({'': pd.NaT, 'nan': pd.NaT, 'None': pd.NaT})
    
    # 1. Tratar numéricos (Excel serial date)
    is_numeric = pd.to_numeric(s, errors='coerce').notna() & ~s.apply(lambda x: isinstance(x, str) and (':' in x or '/' in x or '-' in x))
    if is_numeric.any():
        excel_epoch = pd.Timestamp('1899-12-30')
        s.loc[is_numeric] = excel_epoch + pd.to_timedelta(pd.to_numeric(s.loc[is_numeric]), unit='D')
    
    # 2. Corrigir formato "16:24:00:00" do Google Sheets
    is_str = s.apply(lambda x: isinstance(x, str))
    if is_str.any():
        s.loc[is_str] = s.loc[is_str].apply(
            lambda x: ':'.join(x.split(':')[:3]) if isinstance(x, str) and x.count(':') == 3 else x
        )
    
    # 3. Conversão vetorizada
    result = pd.to_datetime(s, dayfirst=True, errors='coerce')
    
    if not preservar_hora:
        result = result.dt.normalize()
    
    return result


def converter_numero_flexivel(series):
    """
    Converte numeros em formatos pt-BR e en-US para float.
    Exemplos: "1.234,56" -> 1234.56, "0,00092054" -> 0.00092054, "370436.00" -> 370436.0
    """
    s = series.astype(str).str.strip()
    s = s.replace({'': pd.NA, 'nan': pd.NA, 'None': pd.NA})

    mask_both = s.str.contains(r'\.') & s.str.contains(',')
    s.loc[mask_both] = s.loc[mask_both].str.replace('.', '', regex=False).str.replace(',', '.', regex=False)

    mask_comma = s.str.contains(',') & ~s.str.contains(r'\.')
    s.loc[mask_comma] = s.loc[mask_comma].str.replace(',', '.', regex=False)

    return pd.to_numeric(s, errors='coerce').fillna(0.0)


def calcular_mes_competencia(data_compra, cartao=""):
    """
    Calcula o mês de competência com base no dia de fechamento do cartão
    """
    if pd.isna(data_compra): 
        return pd.NaT
    dia_fechamento = FECHAMENTO_CARTOES.get(cartao, 8)
    if data_compra.day <= dia_fechamento:
        return data_compra.to_period("M").to_timestamp()
    else:
        return (data_compra + DateOffset(months=1)).to_period("M").to_timestamp()


def obter_cdi_historico(data_inicio):
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