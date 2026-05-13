import pandas as pd
import re
from sqlalchemy import create_engine
from utils.logging_config import get_logger

logger = get_logger(__name__)

# Configuração do Banco de Dados
DB_URL = "postgresql://admin_finance:Eu120105_@localhost:5432/financial_db"
engine = create_engine(DB_URL)

# Mapeamento do nome da Aba do Sheets para o nome da Tabela no PostgreSQL
TABELAS_MAP = {
    "DebitoAvulso": "debito_avulso",
    "Receitas": "receitas",
    "ComprasCartao": "compras_cartao",
    "PixParcelado": "pix_parcelado",
    "Investimentos": "investimentos"
}

def normalize_column_names(columns):
    """Aplica a mesma padronização de snake_case usada no bootstrap."""
    normalized = []
    for col in columns:
        col = re.sub(r'[^a-zA-Z0-9]', '_', col)
        col = re.sub(r'(?<!^)([A-Z])', r'_\1', col).lower()
        col = re.sub(r'_+', '_', col).strip('_')
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
