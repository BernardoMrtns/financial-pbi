from __future__ import annotations

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from gspread.exceptions import SpreadsheetNotFound, WorksheetNotFound
from requests import RequestException

from config import CREDENTIALS_FILE, SCOPES, SPREADSHEET_ID
from utils.logging_config import get_logger
from utils.retry import retry_call

logger = get_logger(__name__)


def conectar_google_sheets() -> gspread.Spreadsheet:
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)

    return retry_call(
        lambda: client.open_by_key(SPREADSHEET_ID),
        (SpreadsheetNotFound, RequestException, gspread.exceptions.APIError),
        "conexao com Google Sheets",
    )


def carregar_aba(
    spreadsheet: gspread.Spreadsheet,
    nome_aba: str,
    colunas_esperadas: list[str],
) -> pd.DataFrame:
    try:
        worksheet = spreadsheet.worksheet(nome_aba)

        data = retry_call(
            lambda: worksheet.get_all_records(
                empty2zero=False,
                head=1,
                default_blank="",
                value_render_option="UNFORMATTED_VALUE",
            ),
            (gspread.exceptions.APIError, RequestException),
            f"leitura da aba {nome_aba}",
        )

        df = pd.DataFrame(data).dropna(how="all")
        for col in colunas_esperadas:
            if col not in df.columns:
                df[col] = ""
        return df
    except WorksheetNotFound:
        logger.warning("Aba %s nao encontrada. Retornando DataFrame vazio.", nome_aba)
        return pd.DataFrame(columns=colunas_esperadas)


def salvar_aba(spreadsheet: gspread.Spreadsheet, nome_aba: str, df: pd.DataFrame) -> None:
    df_copy = _normalizar_dataframe_para_upload(df.copy(), nome_aba)
    dados_upload = [df_copy.columns.values.tolist()] + df_copy.values.tolist()

    nome_aba_temp = f"{nome_aba}_temp"

    try:
        ws_temp = spreadsheet.worksheet(nome_aba_temp)
        spreadsheet.del_worksheet(ws_temp)
    except WorksheetNotFound:
        pass

    linhas = max(1000, len(dados_upload) + 10)
    ws_temp = spreadsheet.add_worksheet(
        title=nome_aba_temp,
        rows=linhas,
        cols=max(20, len(df_copy.columns)),
    )

    retry_call(
        lambda: ws_temp.update(dados_upload),
        (gspread.exceptions.APIError, RequestException),
        f"upload da aba temporaria {nome_aba_temp}",
    )

    try:
        ws_antiga = spreadsheet.worksheet(nome_aba)
        spreadsheet.del_worksheet(ws_antiga)
    except WorksheetNotFound:
        pass

    ws_temp.update_title(nome_aba)


def adicionar_linha_aba(spreadsheet: gspread.Spreadsheet, nome_aba: str, df_novas_linhas: pd.DataFrame) -> None:
    if df_novas_linhas.empty:
        return

    try:
        worksheet = spreadsheet.worksheet(nome_aba)
    except WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=nome_aba, rows=1000, cols=20)
        worksheet.update("A1", [df_novas_linhas.columns.tolist()])

    df_copy = _normalizar_dataframe_para_upload(df_novas_linhas.copy(), nome_aba)

    header_sheet = worksheet.row_values(1)
    header_df = df_copy.columns.tolist()

    if not header_sheet:
        worksheet.update("A1", [header_df])
        header_sheet = header_df
    elif header_sheet != header_df:
        if nome_aba == "InvestimentoCDI" and header_sheet == ["Data", "ValorCDI"] and header_df == ["DataHora", "ValorCDI"]:
            worksheet.update("A1", [["DataHora", "ValorCDI"]])
            header_sheet = ["DataHora", "ValorCDI"]
        else:
            raise ValueError(
                f"Cabecalho incompativel em {nome_aba}. Esperado={header_sheet} Recebido={header_df}"
            )

    rows_to_append = df_copy.values.tolist()
    linhas_necessarias = len(rows_to_append) + len(worksheet.get_all_values()) + 5

    if linhas_necessarias > worksheet.row_count:
        worksheet.add_rows(linhas_necessarias - worksheet.row_count)

    retry_call(
        lambda: worksheet.append_rows(rows_to_append, value_input_option="USER_ENTERED"),
        (gspread.exceptions.APIError, RequestException),
        f"append em lote na aba {nome_aba}",
    )


def _normalizar_dataframe_para_upload(df: pd.DataFrame, nome_aba: str) -> pd.DataFrame:
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            if nome_aba in {"InvestimentoBTC", "InvestimentoCripto", "InvestimentoCDI"}:
                df[col] = df[col].dt.strftime("%d/%m/%Y %H:%M:%S")
            else:
                df[col] = df[col].dt.strftime("%d/%m/%Y")
            df[col] = df[col].astype(str).str.replace("NaT", "", regex=False)
        df[col] = df[col].replace("nan", "")

    return df.fillna("")
