import pandas as pd
import requests
from pandas.tseries.offsets import DateOffset
from config import DIA_FECHAMENTO_CARTAO


def converter_data_flexivel(series, preservar_hora=False):
    """
    Converte datas em múltiplos formatos (Serial Date do Excel, dd/mm/yyyy ou dd/mm/yyyy hh:mm:ss)
    Otimizado para formato brasileiro
    
    Args:
        series: Série com datas para converter
        preservar_hora: Se True, mantém informação de hora quando disponível
    """
    # Força dtype para datetime64[ns] para suportar precisão de nanosegundos
    result = pd.Series([pd.NaT] * len(series), index=series.index, dtype='datetime64[ns]')
    
    for idx, valor in series.items():
        # Ignora valores vazios
        if pd.isna(valor) or valor == '' or valor == 'NaT':
            continue
        
        # 1. Tenta converter valores numéricos (Serial Date do Excel)
        # Aceita int, float e tipos numéricos do pandas/numpy
        try:
            valor_numerico = pd.to_numeric(valor, errors='coerce')
            if pd.notna(valor_numerico):
                # Serial date do Excel: quantidade de dias desde 30/12/1899
                # Converte para timestamp pandas
                excel_epoch = pd.Timestamp('1899-12-30')
                dias = pd.Timedelta(days=float(valor_numerico))
                data_convertida = excel_epoch + dias
                result[idx] = data_convertida
                continue
        except:
            pass
        
        # 2. Tenta converter strings - FORMATO BRASILEIRO PRIORITÁRIO
        if isinstance(valor, str):
            # Remove espaços extras
            valor = valor.strip()
            
            # Fix: Google Sheets às vezes exporta com formato errado (16:24:00:00)
            # Corrige formato com segundos duplicados
            if valor.count(':') == 3:  # hh:mm:ss:00 (erro do Sheets)
                partes = valor.split(':')
                if len(partes) == 4:
                    valor = ':'.join(partes[:3])  # Remove o último :00
            
            # Tenta formatos brasileiros explicitamente
            formatos_br = [
                '%d/%m/%Y %H:%M:%S',  # 08/02/2026 14:30:00
                '%d/%m/%Y %H:%M',     # 08/02/2026 14:30
                '%d/%m/%Y',           # 08/02/2026
                '%d-%m-%Y %H:%M:%S',  # 08-02-2026 14:30:00
                '%d-%m-%Y',           # 08-02-2026
            ]
            
            for formato in formatos_br:
                try:
                    result[idx] = pd.to_datetime(valor, format=formato)
                    break
                except:
                    continue
            
            # Se ainda não converteu, tenta com dayfirst=True (genérico)
            if pd.isna(result[idx]):
                try:
                    result[idx] = pd.to_datetime(valor, dayfirst=True)
                except:
                    pass
    
    # Se não deve preservar hora, normaliza para meia-noite
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