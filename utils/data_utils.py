from __future__ import annotations

import calendar
from typing import Any

import pandas as pd
import requests
from pandas.tseries.offsets import DateOffset
from requests import RequestException

from config import BACEN_CDI_SERIE_URL, REQUEST_TIMEOUT_SECONDS, VENCIMENTO_CARTOES, DIAS_FECHAMENTO_CARTOES
from utils.logging_config import get_logger
from utils.retry import retry_call

logger = get_logger(__name__)


def converter_data_flexivel(series: pd.Series, preservar_hora: bool = False) -> pd.Series:
    s = series.copy().astype(object)
    s = s.replace({"": pd.NaT, "nan": pd.NaT, "None": pd.NaT})

    is_numeric = pd.to_numeric(s, errors="coerce").notna() & ~s.apply(
        lambda x: isinstance(x, str) and (":" in x or "/" in x or "-" in x)
    )
    if is_numeric.any():
        excel_epoch = pd.Timestamp("1899-12-30")
        s.loc[is_numeric] = excel_epoch + pd.to_timedelta(pd.to_numeric(s.loc[is_numeric]), unit="D")

    is_str = s.apply(lambda x: isinstance(x, str))
    if is_str.any():
        s.loc[is_str] = s.loc[is_str].apply(
            lambda x: ":".join(x.split(":")[:3]) if isinstance(x, str) and x.count(":") == 3 else x
        )
        mask_time_only = s.loc[is_str].str.fullmatch(r"\d{1,2}:\d{2}:\d{2}", na=False)
        s.loc[s.loc[is_str][mask_time_only].index] = pd.NaT

    result = pd.to_datetime(s, dayfirst=True, errors="coerce")
    if not preservar_hora:
        result = result.dt.normalize()
    return result


def converter_numero_flexivel(valor: Any) -> Any:
    """Converte números flexíveis, aceitando tanto pd.Series (ETL) quanto valores únicos (Telegram)."""
    
    # Verifica se é um valor único (string/float) ou uma coluna do Pandas
    is_single_value = not isinstance(valor, pd.Series)
    
    # Se for valor único, embrulha numa Series temporária para reaproveitar a lógica
    s = pd.Series([valor]) if is_single_value else valor.copy()

    s = s.astype(str).str.strip()
    s = s.replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})

    mask_both = s.str.contains(r"\.") & s.str.contains(",")
    s.loc[mask_both] = s.loc[mask_both].str.replace(".", "", regex=False).str.replace(",", ".", regex=False)

    mask_comma = s.str.contains(",") & ~s.str.contains(r"\.")
    s.loc[mask_comma] = s.loc[mask_comma].str.replace(",", ".", regex=False)

    resultado = pd.to_numeric(s, errors="coerce").fillna(0.0)

    # Se era um valor único do Bot, devolve um float puro (ex: 18.88). 
    # Se era do ETL, devolve a coluna inteira do Pandas.
    if is_single_value:
        return float(resultado.iloc[0])
    return resultado


def normalizar_nome_cartao(cartao: str) -> str:
    return str(cartao).strip()


def calcular_mes_competencia(data_compra: pd.Timestamp, cartao: str = "") -> pd.Timestamp:
    if pd.isna(data_compra):
        return pd.NaT

    nome_cartao = normalizar_nome_cartao(cartao)
    dia_vencimento = VENCIMENTO_CARTOES.get(nome_cartao, 8)

    
    nome_upper = str(nome_cartao).upper().replace(" ", "")
    dias_gap = next((gap for banco, gap in DIAS_FECHAMENTO_CARTOES.items() if banco in nome_upper), 8)

    # 1. Identifica o mês base inicial
    if data_compra.day > dia_vencimento:
        mes_base = data_compra + pd.DateOffset(months=1)
    else:
        mes_base = data_compra
        
    # 2. Lógica IMPENETRÁVEL para garantir dias válidos no mês (Trata Fev e meses de 30 dias perfeitamente)
    _, ultimo_dia_mes = calendar.monthrange(mes_base.year, mes_base.month)
    dia_valido = min(dia_vencimento, ultimo_dia_mes)
    data_vencimento_base = pd.Timestamp(year=mes_base.year, month=mes_base.month, day=dia_valido)
        
    # 3. Calcula quando a fatura fecha e o "melhor dia"
    data_fechamento_base = data_vencimento_base - pd.Timedelta(days=dias_gap)
    
    # 4. Avaliação final com operador estrito
    if data_compra < data_fechamento_base:
        return data_vencimento_base.to_period("M").to_timestamp()
    else:
        # Pula para o vencimento do mês seguinte (garantindo também que seja um dia válido)
        mes_seguinte = data_vencimento_base + pd.DateOffset(months=1)
        _, ultimo_dia_mes_seguinte = calendar.monthrange(mes_seguinte.year, mes_seguinte.month)
        dia_valido_seguinte = min(dia_vencimento, ultimo_dia_mes_seguinte)
        
        resultado_final = pd.Timestamp(year=mes_seguinte.year, month=mes_seguinte.month, day=dia_valido_seguinte)
        return resultado_final.to_period("M").to_timestamp()


def obter_cdi_historico(data_inicio: pd.Timestamp) -> pd.DataFrame:
    try:
        data_inicio = pd.Timestamp(data_inicio).normalize()
        data_fim = pd.Timestamp.today().normalize()
        data_busca = data_inicio - pd.Timedelta(days=30)

        def fetch_cdi() -> Any:
            response = requests.get(
                BACEN_CDI_SERIE_URL,
                params={
                    "formato": "json",
                    "dataInicial": data_busca.strftime("%d/%m/%Y"),
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.json()

        raw_data = retry_call(fetch_cdi, (RequestException,), "consulta serie CDI")
        df_cdi = pd.DataFrame(raw_data)
        if df_cdi.empty:
            return pd.DataFrame(columns=["Data", "FatorDiario"])

        df_cdi["Data"] = pd.to_datetime(df_cdi["data"], format="%d/%m/%Y")
        df_cdi["Taxa"] = pd.to_numeric(
            df_cdi["valor"].astype(str).str.replace(",", ".", regex=False),
            errors="coerce",
        )
        df_cdi["FatorDiario"] = 1 + (df_cdi["Taxa"] / 100)
        df_cdi = df_cdi.dropna(subset=["Data", "FatorDiario"]).sort_values("Data")

        indice_calendario = pd.date_range(start=data_inicio, end=data_fim, freq="D")
        if indice_calendario.empty:
            return pd.DataFrame(columns=["Data", "FatorDiario"])

        df_cdi = df_cdi.set_index("Data").reindex(indice_calendario)
        df_cdi.index.name = "Data"
        df_cdi["FatorDiario"] = df_cdi["FatorDiario"].ffill().bfill().fillna(1.0)
        return df_cdi.reset_index()[["Data", "FatorDiario"]]
    except RuntimeError as error:
        logger.error("Falha ao buscar historico CDI: %s", error)
        return pd.DataFrame(columns=["Data", "FatorDiario"])


def calcular_fator_cdi_periodo(
    data_inicio: pd.Timestamp,
    data_fim: pd.Timestamp,
    df_historico_cdi: pd.DataFrame,
) -> float:
    if df_historico_cdi.empty:
        return 1.0

    inicio = pd.Timestamp(data_inicio)
    fim = pd.Timestamp(data_fim)

    if pd.isna(inicio) or pd.isna(fim) or fim <= inicio:
        return 1.0

    historico = df_historico_cdi.copy()
    historico["Data"] = pd.to_datetime(historico["Data"], errors="coerce").dt.normalize()
    historico["FatorDiario"] = pd.to_numeric(historico["FatorDiario"], errors="coerce").fillna(1.0)
    fatores = historico.dropna(subset=["Data"]).set_index("Data")["FatorDiario"].to_dict()

    fator_acumulado = 1.0
    cursor = inicio

    while cursor < fim:
        inicio_dia = cursor.normalize()
        proximo_dia = inicio_dia + pd.Timedelta(days=1)
        limite = min(fim, proximo_dia)
        segundos_no_trecho = (limite - cursor).total_seconds()
        fracao_dia = segundos_no_trecho / 86400
        fator_dia = fatores.get(inicio_dia, 1.0)
        fator_acumulado *= fator_dia ** fracao_dia
        cursor = limite

    return fator_acumulado