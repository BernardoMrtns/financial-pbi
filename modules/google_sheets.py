"""
Módulo para integração com Google Sheets
"""
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from config import CREDENTIALS_FILE, SCOPES, SPREADSHEET_ID


def conectar_google_sheets():
    """
    Conecta ao Google Sheets e retorna o spreadsheet
    """
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID)


def carregar_aba(spreadsheet, nome_aba, colunas_esperadas):
    """
    Carrega uma aba do Google Sheets como DataFrame
    """
    try:
        worksheet = spreadsheet.worksheet(nome_aba)
        # Mantemos UNFORMATTED_VALUE para preservar números decimais corretos e datas serial
        data = worksheet.get_all_records(
            empty2zero=False,
            head=1,
            default_blank='',
            value_render_option='UNFORMATTED_VALUE'
        )
        df = pd.DataFrame(data)
        df = df.dropna(how='all')
        # Garante que todas colunas esperadas existam
        for col in colunas_esperadas:
            if col not in df.columns:
                df[col] = ""
        return df
    except Exception as e:
        print(f"⚠️ Aviso: Aba '{nome_aba}' não encontrada ou vazia. Criando vazia.")
        return pd.DataFrame(columns=colunas_esperadas)


def salvar_aba(spreadsheet, nome_aba, df):
    """
    Salva um DataFrame em uma aba do Google Sheets
    """
    try:
        worksheet = spreadsheet.worksheet(nome_aba)
        worksheet.clear()
    except:
        worksheet = spreadsheet.add_worksheet(title=nome_aba, rows=1000, cols=20)

    df_copy = df.copy()
    # Converte datas para string dd/mm/yyyy para visualização no Sheets
    for col in df_copy.columns:
        if pd.api.types.is_datetime64_any_dtype(df_copy[col]):
            df_copy[col] = df_copy[col].dt.strftime('%d/%m/%Y')
            df_copy[col] = df_copy[col].astype(str).str.replace('NaT', '', regex=False)
        df_copy[col] = df_copy[col].replace('nan', '')

    df_copy = df_copy.fillna('')

    # Prepara lista de listas para upload
    dados_upload = [df_copy.columns.values.tolist()] + df_copy.values.tolist()
    worksheet.update(dados_upload)