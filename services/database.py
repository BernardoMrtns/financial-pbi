import pandas as pd
import re
import os
from sqlalchemy import create_engine, text
from utils.logging_config import get_logger
from config import DB_URL
os.environ["PGCLIENTENCODING"] = "utf-8"

logger = get_logger(__name__)

# Configuração: Forçamos o client_encoding para utf8.
# Isso garante que o Python consiga ler os "ç" e "ã" das mensagens de erro do banco sem crashar.
engine = create_engine(DB_URL, connect_args={'client_encoding': 'utf8'})

# Mapeamento do nome da Aba do Sheets para o nome da Tabela no PostgreSQL
TABELAS_MAP = {
    "DebitoAvulso": "debito_avulso",
    "Receitas": "receitas",
    "ComprasCartao": "compras_cartao",
    "PixParcelado": "pix_parcelado",
    "Investimentos": "investimentos",
    "FluxoCaixaCompleto": "fluxo_caixa",
    "InvestimentoCDI": "investimento_cdi",
    "InvestimentoBTC": "investimento_btc",
    "InvestimentoCripto": "investimento_cripto"
}

def normalize_column_names(columns):
    """Converte cabeçalhos para snake_case, protegendo siglas definidas no mapa."""
    MAPA_MANUAL = {
        'valor_c_d_i': 'valor_cdi',
        'saldo_b_t_c': 'saldo_btc',
        'preco_b_t_c': 'preco_btc'
    }
    
    normalized = []
    for col in columns:
        col = re.sub(r'[^a-zA-Z0-9]', '_', col)
        col = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', col).lower()
        col = re.sub(r'_+', '_', col).strip('_')
        col = MAPA_MANUAL.get(col, col)
        normalized.append(col)
    return normalized

def adicionar_linha_db(nome_aba: str, df: pd.DataFrame) -> None:
    """Recebe o DataFrame normalizado pelo Telegram bot e insere no PostgreSQL."""
    tabela = TABELAS_MAP.get(nome_aba)
    if not tabela:
        logger.error(f"Tabela no PostgreSQL não mapeada para a aba: {nome_aba}")
        return
        
    try:
        df_db = df.copy()
        df_db.columns = normalize_column_names(df_db.columns)
        
        # Insere no PostgreSQL (if_exists='append' adiciona a nova linha à tabela existente)
        df_db.to_sql(tabela, engine, if_exists='append', index=False)
        logger.info(f"Linha adicionada com sucesso no PostgreSQL -> tabela '{tabela}'")
    except Exception as e:
        logger.error(f"Erro ao salvar no PostgreSQL (tabela {tabela}): {e}")

def atualizar_tabela_completa(nome_aba: str, df: pd.DataFrame) -> None:
    """Sobrescreve completamente os dados da tabela, mantendo a estrutura original."""
    tabela = TABELAS_MAP.get(nome_aba)
    if not tabela:
        logger.error(f"Tabela no PostgreSQL não mapeada para a aba: {nome_aba}")
        return

    try:
        df_db = df.copy()
        df_db.columns = normalize_column_names(df_db.columns)

        # A MÁGICA DE ENGENHARIA DE DADOS:
        # Em vez de apagar a tabela ('replace'), nós limpamos as linhas (DELETE) e colamos as novas.
        # Isso preserva a sua coluna 'id' (Primary Key) e mantém o cadeado do pgAdmin destrancado!
        with engine.begin() as conn:
            try:
                conn.execute(text(f"DELETE FROM {tabela};"))
            except Exception as e:
                # Se a tabela ainda não existir, o banco avisa, nós ignoramos e deixamos o Pandas criá-la.
                pass

        df_db.to_sql(tabela, engine, if_exists='append', index=False)
        logger.info(f"Tabela '{tabela}' atualizada com sucesso (delete & append).")
    except Exception as e:
        logger.error(f"Erro ao atualizar tabela '{tabela}' no PostgreSQL: {e}")