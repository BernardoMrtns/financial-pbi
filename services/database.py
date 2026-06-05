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
    "InvestimentoCripto": "investimento_cripto",
    "FaturasPagas": "faturas_pagas",
    "Assinaturas": "assinaturas",
    "Wishlist": "wishlist"
}

def normalize_column_names(columns):
    """Converte cabeçalhos para snake_case, protegendo siglas definidas no mapa."""
    MAPA_MANUAL = {
        'valor_c_d_i': 'valor_cdi',
        'saldo_b_t_c': 'saldo_btc',
        'preco_b_t_c': 'preco_btc',
        'pre_o': 'preco'  # <--- Nova linha adicionada!
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
        raise e

def atualizar_tabela_completa(nome_aba: str, df: pd.DataFrame) -> None:
    """Sobrescreve completamente os dados da tabela, mantendo a estrutura original e resetando o ID."""
    tabela = TABELAS_MAP.get(nome_aba)
    if not tabela:
        logger.error(f"Tabela no PostgreSQL não mapeada para a aba: {nome_aba}")
        return

    try:
        df_db = df.copy()
        df_db.columns = normalize_column_names(df_db.columns)

        with engine.begin() as conn:
            try:
                # A MÁGICA ATUALIZADA:
                # TRUNCATE esvazia a tabela instantaneamente.
                # RESTART IDENTITY garante que a coluna 'id' volte para 1.
                # CASCADE garante que limpe mesmo se houver dependências (opcional, mas seguro em data warehouses).
                conn.execute(text(f"TRUNCATE TABLE {tabela} RESTART IDENTITY CASCADE;"))
            except Exception as e:
                # Se a tabela ainda não existir, o banco avisa, nós ignoramos e deixamos o Pandas criá-la na primeira vez.
                pass

        # Insere os dados novos (agora com o ID recomeçando do 1)
        df_db.to_sql(tabela, engine, if_exists='append', index=False)
        logger.info(f"Tabela '{tabela}' atualizada com sucesso (TRUNCATE & append).")
    except Exception as e:
        logger.error(f"Erro ao atualizar tabela '{tabela}' no PostgreSQL: {e}")

# ==========================================
#        NOVAS FUNÇÕES PARA O BOT (UPDATE/SELECT)
# ==========================================

def buscar_registro_db(nome_aba: str, coluna_chave: str, valor_chave: any) -> dict:
    """Busca um único registo na base de dados com base numa chave."""
    tabela = TABELAS_MAP.get(nome_aba, nome_aba)
    
    col_chave_norm = normalize_column_names([coluna_chave])[0]
    query = text(f"SELECT * FROM {tabela} WHERE {col_chave_norm} = :valor_chave LIMIT 1")
    
    try:
        with engine.connect() as conn:
            result = conn.execute(query, {"valor_chave": valor_chave}).mappings().fetchone()
            return dict(result) if result else {}
    except Exception as e:
        logger.error(f"Erro ao buscar na tabela {tabela}: {e}")
        return {}

def atualizar_registro_db(nome_aba: str, coluna_chave: str, valor_chave: any, dados_atualizacao: dict) -> None:
    """
    Atualiza um ou mais campos de um registo específico na base de dados PostgreSQL.
    Ex: atualizar_registro_db("FaturasPagas", "cartao", "Nubank", {"ultimo_ciclo_pago": "01/06/2026"})
    """
    tabela = TABELAS_MAP.get(nome_aba, nome_aba)
    if not tabela:
        logger.error(f"Tabela não mapeada para a aba: {nome_aba}")
        return
        
    col_chave_norm = normalize_column_names([coluna_chave])[0]
    
    set_clauses = []
    params = {"valor_chave": valor_chave}
    
    # Montar a query dinamicamente com as colunas normalizadas (snake_case)
    for key, value in dados_atualizacao.items():
        col_norm = normalize_column_names([key])[0]
        param_name = f"val_{col_norm}"
        set_clauses.append(f"{col_norm} = :{param_name}")
        params[param_name] = value
        
    set_query = ", ".join(set_clauses)
    query = text(f"UPDATE {tabela} SET {set_query} WHERE {col_chave_norm} = :valor_chave")
    
    try:
        with engine.begin() as conn:
            result = conn.execute(query, params)
            logger.info(f"DB -> Tabela '{tabela}': {result.rowcount} registo(s) atualizado(s).")
    except Exception as e:
        logger.error(f"Erro ao atualizar {tabela} no PostgreSQL: {e}")

def ler_tabela_db(nome_aba: str) -> pd.DataFrame:
    """Lê uma tabela inteira do PostgreSQL e retorna como DataFrame."""
    tabela = TABELAS_MAP.get(nome_aba)
    if not tabela:
        logger.error(f"Tabela no PostgreSQL não mapeada para a aba: {nome_aba}")
        return pd.DataFrame()
        
    try:
        # Lê a tabela diretamente usando o pandas e a engine do SQLAlchemy
        with engine.connect() as conn:
            df = pd.read_sql_table(tabela, conn)
        return df
    except Exception as e:
        logger.error(f"Erro ao ler tabela '{tabela}' do PostgreSQL: {e}")
        return pd.DataFrame()