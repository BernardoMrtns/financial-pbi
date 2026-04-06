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
    Salva um DataFrame em uma aba do Google Sheets (Usando Padrão Swap para segurança)
    Para abas de snapshot de cripto, preserva Date/Time completo para maior precisão
    """
    df_copy = df.copy()
    # Converte datas para string
    for col in df_copy.columns:
        if pd.api.types.is_datetime64_any_dtype(df_copy[col]):
            # Para snapshots de cripto, usa formato com data e hora completa
            if nome_aba in {"InvestimentoBTC", "InvestimentoCripto"}:
                df_copy[col] = df_copy[col].dt.strftime('%d/%m/%Y %H:%M:%S')
            else:
                # Outras abas usam apenas data
                df_copy[col] = df_copy[col].dt.strftime('%d/%m/%Y')
            df_copy[col] = df_copy[col].astype(str).str.replace('NaT', '', regex=False)
        df_copy[col] = df_copy[col].replace('nan', '')

    df_copy = df_copy.fillna('')

    # Prepara lista de listas para upload
    dados_upload = [df_copy.columns.values.tolist()] + df_copy.values.tolist()
    
    nome_aba_temp = f"{nome_aba}_temp"
    
    # 1. Remove aba temporária se existir (resíduo de erro anterior)
    try:
        ws_temp = spreadsheet.worksheet(nome_aba_temp)
        spreadsheet.del_worksheet(ws_temp)
    except Exception:
        pass
        
    # 2. Cria aba temporária e envia os dados
    linhas = max(1000, len(dados_upload) + 10)
    ws_temp = spreadsheet.add_worksheet(title=nome_aba_temp, rows=linhas, cols=max(20, len(df_copy.columns)))
    ws_temp.update(dados_upload)
    
    # 3. Remove aba antiga original e renomeia a temporária
    try:
        ws_antiga = spreadsheet.worksheet(nome_aba)
        spreadsheet.del_worksheet(ws_antiga)
    except Exception:
        pass
        
    ws_temp.update_title(nome_aba)


def adicionar_linha_aba(spreadsheet, nome_aba, df_nova_linha):
    """
    Adiciona uma nova linha ao final de uma aba do Google Sheets
    Útil para histórico incremental como InvestimentoBTC
    """
    try:
        worksheet = spreadsheet.worksheet(nome_aba)
    except:
        # Se a aba não existe, cria com cabeçalho
        worksheet = spreadsheet.add_worksheet(title=nome_aba, rows=1000, cols=20)
        # Adiciona cabeçalho
        worksheet.append_row(df_nova_linha.columns.tolist())
    
    df_copy = df_nova_linha.copy()
    
    # Converte datas para string com hora completa para InvestimentoBTC
    for col in df_copy.columns:
        if pd.api.types.is_datetime64_any_dtype(df_copy[col]):
            df_copy[col] = df_copy[col].dt.strftime('%d/%m/%Y %H:%M:%S')
            df_copy[col] = df_copy[col].astype(str).str.replace('NaT', '', regex=False)
        df_copy[col] = df_copy[col].replace('nan', '')
    
    df_copy = df_copy.fillna('')
    
    # Adiciona cada linha do DataFrame
    for _, row in df_copy.iterrows():
        worksheet.append_row(row.tolist())