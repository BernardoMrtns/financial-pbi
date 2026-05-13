import pandas as pd
import re
from sqlalchemy import create_engine

# Database connection string
DB_URL = "postgresql://admin_finance:Eu120105_@localhost:5432/financial_db"
engine = create_engine(DB_URL)

def normalize_column_names(columns):
    """Converts 'ContaDestino' or 'Conta Saída' to 'conta_destino'."""
    normalized = []
    for col in columns:
        # Remove accents, replace spaces with underscores, convert to lowercase
        col = re.sub(r'[^a-zA-Z0-9]', '_', col)
        col = re.sub(r'(?<!^)(=[A-Z])', r'_\1', col).lower()
        # Clean up multiple underscores
        col = re.sub(r'_+', '_', col).strip('_')
        normalized.append(col)
    return normalized

def clean_financial_data(df):
    """Handles the Pandas dtype warnings by explicitly cleaning and casting."""
    df.columns = normalize_column_names(df.columns)
    
    for col in df.columns:
        # Clean Currency/Numeric columns (e.g., "R$ 2.551,00" -> 2551.00)
        if 'valor' in col or 'preco' in col or 'saldo' in col or 'limite' in col:
            df[col] = (df[col].astype(str)
                       .str.replace('R$', '', regex=False)
                       .str.replace('.', '', regex=False)
                       .str.replace(',', '.', regex=False)
                       .str.strip())
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
        # Clean Date columns (e.g., "28/12/2025")
        elif 'data' in col or 'inicio' in col or col == 'fim':
            df[col] = pd.to_datetime(df[col], format='%d/%m/%Y', errors='ignore')
            # Handle datetime columns like DataHora
            if df[col].dtype == 'object':
                df[col] = pd.to_datetime(df[col], format='%d/%m/%Y %H:%M:%S', errors='coerce')
                
    return df

def migrate_table(df, table_name):
    print(f"Migrating {table_name}...")
    cleaned_df = clean_financial_data(df.copy())
    
    # Write to PostgreSQL. 'replace' is fine for the initial bootstrap.
    cleaned_df.to_sql(table_name, engine, if_exists='replace', index=False)
    print(f"Successfully migrated {len(cleaned_df)} rows to '{table_name}'.")

# Example usage assuming you have your existing Google Sheets loading logic
# df_receitas = load_from_google_sheets("Receitas") 
# migrate_table(df_receitas, 'receitas')