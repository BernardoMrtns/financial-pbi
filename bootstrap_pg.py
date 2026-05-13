import os
import pandas as pd
import re
from sqlalchemy import create_engine, text

# --- DATABASE CONFIGURATION ---
# Replace 'your_secure_password' with the password you set in PostgreSQL
DB_URL = "postgresql://admin_finance:Eu120105_@localhost:5432/financial_db"
engine = create_engine(DB_URL)

def normalize_column_names(columns):
    """Converts headers like 'ValorCDI' to 'valor_cdi' instead of 'valor_c_d_i'."""
    normalized = []
    for col in columns:
        # 1. Remove caracteres especiais
        col = re.sub(r'[^a-zA-Z0-9]', '_', col)
        
        # 2. Lógica para siglas: Mantém sequências de maiúsculas juntas
        # Ex: ValorCDI -> Valor_CDI
        col = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', col)
        
        # 3. Converte para minúsculo
        col = col.lower()
        
        # 4. Limpa underlines duplicados
        col = re.sub(r'_+', '_', col).strip('_')
        normalized.append(col)
    return normalized

def clean_financial_data(df):
    """Cleans currency strings, normalizes types, and parses dates."""
    df.columns = normalize_column_names(df.columns)
    
    for col in df.columns:
        # Clean Currency/Numeric columns (e.g., "R$ 2.551,00" -> 2551.00)
        if 'valor' in col or 'preco' in col or 'saldo' in col or 'limite' in col or 'preço' in col:
            df[col] = (df[col].astype(str)
                       .str.replace('R$', '', regex=False)
                       .str.replace('¥', '', regex=False)
                       .str.replace('.', '', regex=False)
                       .str.replace(',', '.', regex=False)
                       .str.strip())
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
        # Clean Date columns
        elif 'data' in col or 'inicio' in col or col == 'fim':
            # Try basic date first
            df[col] = pd.to_datetime(df[col], format='%d/%m/%Y', errors='ignore')
            # If it's still a string/object, try with time included
            if df[col].dtype == 'object':
                df[col] = pd.to_datetime(df[col], format='%d/%m/%Y %H:%M:%S', errors='coerce')
                
    return df

def migrate_table(df, table_name):
    """Writes the dataframe to PostgreSQL and injects an auto-incrementing ID."""
    print(f"Migrating {table_name}...")
    cleaned_df = clean_financial_data(df.copy())
    
    # 1. Write the flat data to PostgreSQL. 
    # 'replace' drops the old table and makes a fresh one, preventing duplicates during testing.
    cleaned_df.to_sql(table_name, engine, if_exists='replace', index=False)
    
    # 2. Inject a Primary Key (ID) column into the table
    try:
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN id SERIAL PRIMARY KEY;"))
    except Exception as e:
        print(f"  -> Note: Could not add Primary Key to {table_name}: {e}")
        
    print(f"  -> Successfully migrated {len(cleaned_df)} rows to '{table_name}'.")

if __name__ == "__main__":
    print("Starting database migration...\n")
    
    # Map your PostgreSQL table names to the CSV files you uploaded
    csv_mappings = {
        "fluxo_caixa": "Finanças - FluxoCaixaCompleto.csv",
        "limites": "Finanças - Limites.csv",
        "investimento_cdi": "Finanças - InvestimentoCDI.csv",
        "investimento_cripto": "Finanças - InvestimentoCripto.csv",
        "investimento_btc": "Finanças - InvestimentoBTC.csv",
        "faturas_pagas": "Finanças - FaturasPagas.csv",
        "investimentos": "Finanças - Investimentos.csv",
        "assinaturas": "Finanças - Assinaturas.csv",
        "pix_parcelado": "Finanças - PixParcelado.csv",
        "compras_cartao": "Finanças - ComprasCartao.csv",
        "debito_avulso": "Finanças - DebitoAvulso.csv",
        "receitas": "Finanças - Receitas.csv",
        "wishlist": "Finanças - Wishlist.csv",
        "wishlist_cssbuy": "Finanças - WishlistCssBuy.csv"
    }

    # Loop through and migrate each file
    for table_name, filename in csv_mappings.items():
        # Assuming the CSVs are in the same folder where you run the script
        file_path = filename 
        
        if os.path.exists(file_path):
            try:
                # Read the CSV (adjusting for potential delimiter or encoding issues if needed)
                df = pd.read_csv(file_path)
                migrate_table(df, table_name)
            except Exception as e:
                print(f"Error processing {filename}: {e}")
        else:
            print(f"Skipping {table_name}: Could not find file '{file_path}'")
            
    print("\nMigration complete! Your data is now safely in PostgreSQL with IDs.")
