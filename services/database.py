import pandas as pd
import re
from sqlalchemy import create_engine
from utils.logging_config import get_logger
from config import DB_URL

logger = get_logger(__name__)

# Configuração do Banco de Dados
engine = create_engine(DB_URL)

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
    import re
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
        # Prepara o DataFrame para o banco
        df_db = df.copy()
        df_db.columns = normalize_column_names(df_db.columns)
        
        # Insere no PostgreSQL (if_exists='append' adiciona a nova linha à tabela existente)
        df_db.to_sql(tabela, engine, if_exists='append', index=False)
        logger.info(f"Linha adicionada com sucesso no PostgreSQL -> tabela '{tabela}'")
    except Exception as e:
        logger.error(f"Erro ao salvar no PostgreSQL (tabela {tabela}): {e}")


def atualizar_tabela_completa(nome_aba: str, df: pd.DataFrame) -> None:
    """Sobrescreve completamente a tabela correspondente no PostgreSQL.

    Recebe o nome da aba (nome_aba) e um DataFrame pandas (df).
    Usa TABELAS_MAP para resolver o nome da tabela no banco. Faz uma cópia
    do DataFrame e normaliza os nomes de coluna com `normalize_column_names`.
    Grava usando if_exists='replace'. Erros são tratados e logados.
    """
    tabela = TABELAS_MAP.get(nome_aba)
    if not tabela:
        logger.error(f"Tabela no PostgreSQL não mapeada para a aba: {nome_aba}")
        return

    try:
        df_db = df.copy()
        df_db.columns = normalize_column_names(df_db.columns)

        df_db.to_sql(tabela, engine, if_exists='replace', index=False)
        logger.info(f"Tabela '{tabela}' atualizada com sucesso (replace).")
    except Exception as e:
        logger.error(f"Erro ao atualizar tabela '{tabela}' no PostgreSQL: {e}")
