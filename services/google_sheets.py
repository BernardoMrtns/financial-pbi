from __future__ import annotations

import time

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError, SpreadsheetNotFound, WorksheetNotFound
from requests import RequestException

from config import CREDENTIALS_FILE, SCOPES, SPREADSHEET_ID
from utils.logging_config import get_logger
from utils.retry import retry_call

logger = get_logger(__name__)


# Colunas monetarias por aba para forcar exibicao como BRL no Google Sheets.
COLUNAS_MOEDA_POR_ABA: dict[str, set[str]] = {
    "Assinaturas": {"Valor"},
    "ComprasCartao": {"ValorTotal"},
    "DebitoAvulso": {"Valor"},
    "InvestimentoBTC": {"Valor"},
    "InvestimentoCDI": {"ValorCDI"},
    "InvestimentoCripto": {"Valor"},
    "Investimentos": {"Valor"},
    "PixParcelado": {"ValorTotal", "ValorEntrada"},
    "Receitas": {"Valor"},
}


def carregar_worksheet_safe(
    spreadsheet: gspread.Spreadsheet,
    nome_aba: str,
    tentativas: int = 5,
) -> gspread.Worksheet:
    last_error: APIError | None = None

    for tentativa in range(tentativas):
        try:
            return spreadsheet.worksheet(nome_aba)
        except APIError as error:
            last_error = error
            if "503" not in str(error):
                raise

            espera = 2 ** tentativa
            logger.warning("Erro 503 ao carregar a aba %s. Retry em %ss...", nome_aba, espera)
            time.sleep(espera)

    raise RuntimeError(f"Falhou ao carregar a aba {nome_aba} apos {tentativas} tentativas") from last_error


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
        worksheet = carregar_worksheet_safe(spreadsheet, nome_aba)

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
        ws_temp = carregar_worksheet_safe(spreadsheet, nome_aba_temp)
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
    _aplicar_formato_moeda(ws_temp, nome_aba, df_copy.columns.tolist())

    try:
        ws_antiga = carregar_worksheet_safe(spreadsheet, nome_aba)
        spreadsheet.del_worksheet(ws_antiga)
    except WorksheetNotFound:
        pass

    ws_temp.update_title(nome_aba)


def adicionar_linha_aba(spreadsheet: gspread.Spreadsheet, nome_aba: str, df_novas_linhas: pd.DataFrame) -> None:
    if df_novas_linhas.empty:
        return

    try:
        worksheet = carregar_worksheet_safe(spreadsheet, nome_aba)
    except WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=nome_aba, rows=1000, cols=20)
        worksheet.update("A1", [df_novas_linhas.columns.tolist()])

    df_copy = _normalizar_dataframe_para_upload(df_novas_linhas.copy(), nome_aba)

    # Get header from sheet - usar row_values() para pegar apenas a primeira linha
    header_sheet = worksheet.row_values(1)
    header_df = df_copy.columns.tolist()

    if not header_sheet:
        logger.info(f"Aba {nome_aba}: Header vazio, criando novo header")
        worksheet.update("A1", [header_df])
        header_sheet = header_df
    elif header_sheet != header_df:
        # Handle specific schema mismatches
        if nome_aba == "InvestimentoCDI" and header_sheet == ["Data", "ValorCDI"] and header_df == ["DataHora", "ValorCDI"]:
            logger.info(f"Aba {nome_aba}: Atualizando header InvestimentoCDI")
            worksheet.update("A1", [["DataHora", "ValorCDI"]])
            header_sheet = ["DataHora", "ValorCDI"]
        # Handle migration from "Data" to "DataHora" in Investimentos aba
        elif nome_aba == "Investimentos" and header_sheet[0] == "Data" and header_df[0] == "DataHora":
            logger.info("Atualizando header da aba Investimentos de 'Data' para 'DataHora'")
            worksheet.update("A1", [header_df])
            header_sheet = header_df
        else:
            # Log detailed mismatch info for debugging
            logger.warning(
                "Cabecalho pode conter espaços ou caracteres diferentes em %s. "
                "Esperado=%s | Recebido=%s | "
                "Esperado (repr)=%r | Recebido (repr)=%r",
                nome_aba, header_sheet, header_df, header_sheet, header_df
            )
            # Strip and compare without whitespace issues
            header_sheet_stripped = [h.strip() if isinstance(h, str) else h for h in header_sheet]
            header_df_stripped = [h.strip() if isinstance(h, str) else h for h in header_df]
            if header_sheet_stripped != header_df_stripped:
                raise ValueError(
                    f"Cabecalho incompativel em {nome_aba}. Esperado={header_sheet} Recebido={header_df}"
                )

    _aplicar_formato_moeda(worksheet, nome_aba, header_sheet)

    rows_to_append = df_copy.values.tolist()
    
    # Get the actual number of rows in the sheet using get_all_records() which excludes empty rows
    try:
        records = worksheet.get_all_records(empty2zero=False)
        current_data_rows = len(records)
    except Exception:
        # Fallback to get_all_values if get_all_records fails
        all_values = worksheet.get_all_values()
        current_data_rows = len(all_values) - 1  # -1 para excluir o header
    
    linhas_necessarias = current_data_rows + 1 + len(rows_to_append) + 5

    logger.debug(f"Aba {nome_aba}: Linhas de dados atuais: {current_data_rows}. Adicionando {len(rows_to_append)} linhas")

    if linhas_necessarias > worksheet.row_count:
        worksheet.add_rows(linhas_necessarias - worksheet.row_count)

    # Write rows starting at the first empty data row (after header).
    # Using an explicit update at the computed start row avoids issues
    # where view-level sorting/filtering can make newly-appended rows
    # appear at the top of the sheet.
    start_row = current_data_rows + 2  # +1 for header, +1 to move to next empty row
    start_cell = f"A{start_row}"

    retry_call(
        lambda: worksheet.update(start_cell, rows_to_append, value_input_option="USER_ENTERED"),
        (gspread.exceptions.APIError, RequestException),
        f"escrita em lote na aba {nome_aba} a partir de {start_cell}",
    )
    logger.info(f"Aba {nome_aba}: {len(rows_to_append)} linha(s) adicionada(s) com sucesso ao final da tabela")


def _normalizar_dataframe_para_upload(df: pd.DataFrame, nome_aba: str) -> pd.DataFrame:
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            # Colunas com hora: DataHora para investimentos, outras abas específicas
            if col == "DataHora" or nome_aba in {"InvestimentoBTC", "InvestimentoCripto", "InvestimentoCDI"}:
                df[col] = df[col].dt.strftime("%d/%m/%Y %H:%M:%S")
            else:
                df[col] = df[col].dt.strftime("%d/%m/%Y")
            df[col] = df[col].astype(str).str.replace("NaT", "", regex=False)
        df[col] = df[col].replace("nan", "")

    return df.fillna("")


def _aplicar_formato_moeda(
    worksheet: gspread.Worksheet,
    nome_aba: str,
    cabecalho: list[str],
) -> None:
    colunas_monetarias = COLUNAS_MOEDA_POR_ABA.get(nome_aba)
    if not colunas_monetarias or not cabecalho:
        return

    requests: list[dict] = []
    for indice_coluna, nome_coluna in enumerate(cabecalho):
        if nome_coluna not in colunas_monetarias:
            continue

        requests.append(
            {
                "repeatCell": {
                    "range": {
                        "sheetId": worksheet.id,
                        "startRowIndex": 1,
                        "startColumnIndex": indice_coluna,
                        "endColumnIndex": indice_coluna + 1,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "numberFormat": {
                                "type": "CURRENCY",
                                "pattern": "R$ #,##0.00",
                            }
                        }
                    },
                    "fields": "userEnteredFormat.numberFormat",
                }
            }
        )

    if not requests:
        return

    retry_call(
        lambda: worksheet.spreadsheet.batch_update({"requests": requests}),
        (gspread.exceptions.APIError, RequestException),
        f"formatacao de moeda BRL na aba {nome_aba}",
    )
