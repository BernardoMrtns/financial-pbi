import pandas as pd
from processors import DataLoader, FluxoCaixaProcessor, PatrimonioCalculator
from services import adicionar_linha_aba, conectar_google_sheets, salvar_aba
from services.database import atualizar_tabela_completa, adicionar_linha_db
from utils import get_logger

logger = get_logger(__name__)

def limpar_dados(df_master, patrimonio):
    """Padroniza e limpa os dados antes de enviar para os destinos."""
    logger.info("Realizando limpeza e tipagem dos dados...")
    
    # 1. LIMPEZA DO FLUXO DE CAIXA
    if not df_master.empty:
        for col in ['DataOriginal', 'DataCompetencia']:
            if col in df_master.columns:
                df_master[col] = pd.to_datetime(df_master[col]).dt.strftime('%Y-%m-%d %H:%M:%S')
        
        for col in ['Valor', 'ValorFluxo']:
            if col in df_master.columns:
                df_master[col] = df_master[col].astype(float).round(2)

    # 2. LIMPEZA DO PATRIMÔNIO (Investimentos)
    for tipo in ['btc', 'cdi', 'cripto']:
        if not patrimonio[tipo].empty:
            df = patrimonio[tipo]
            
            if 'DataHora' in df.columns:
                df['DataHora'] = pd.to_datetime(df['DataHora']).dt.strftime('%Y-%m-%d %H:%M:%S')
            
            for col in ['ValorCDI', 'PrecoBTC', 'ValorReais', 'PrecoCripto']:
                if col in df.columns:
                    df[col] = df[col].astype(float).round(2)
            
            for col in ['SaldoBTC', 'SaldoCripto']:
                if col in df.columns:
                    df[col] = df[col].astype(float).round(8)
                    
    return df_master, patrimonio

def sincronizar_google_sheets(spreadsheet, df_master, patrimonio):
    """Abordagem focada em UI/Backup: Atualiza as abas visuais do usuário."""
    logger.info("--- [1/2] Iniciando carga no Google Sheets ---")
    
    if not df_master.empty:
        try:
            salvar_aba(spreadsheet, "FluxoCaixaCompleto", df_master)
            logger.info("✅ Planilha 'FluxoCaixaCompleto' sobrescrita com sucesso.")
        except Exception as e:
            logger.error(f"❌ Erro ao salvar FluxoCaixaCompleto no Sheets: {e}")

    # Mapeamento do nome interno para o Nome da Aba
    abas_investimento = [('btc', 'InvestimentoBTC'), ('cdi', 'InvestimentoCDI'), ('cripto', 'InvestimentoCripto')]
    
    for tipo, nome_aba in abas_investimento:
        if not patrimonio[tipo].empty:
            try:
                adicionar_linha_aba(spreadsheet, nome_aba, patrimonio[tipo])
                logger.info(f"✅ Nova linha adicionada na aba '{nome_aba}'.")
            except Exception as e:
                logger.error(f"❌ Erro ao adicionar linha em {nome_aba} no Sheets: {e}")

def sincronizar_postgres(df_master, patrimonio):
    """Abordagem focada em Data Warehouse: Prepara as tabelas para o Power BI."""
    logger.info("--- [2/2] Iniciando carga no PostgreSQL ---")
    
    if not df_master.empty:
        try:
            # CORREÇÃO: Passar a chave exata que o TABELAS_MAP espera
            atualizar_tabela_completa("FluxoCaixaCompleto", df_master)
            logger.info("✅ Tabela 'fluxo_caixa' sobrescrita no banco.")
        except Exception as e:
            logger.error(f"❌ Erro ao atualizar fluxo_caixa no Postgres: {e}")

    # CORREÇÃO: Passar as chaves exatas que o TABELAS_MAP espera
    tabelas_investimento = [('btc', 'InvestimentoBTC'), ('cdi', 'InvestimentoCDI'), ('cripto', 'InvestimentoCripto')]
    
    for tipo, nome_aba in tabelas_investimento:
        if not patrimonio[tipo].empty:
            try:
                # O database.py vai tratar de converter para snake_case internamente
                adicionar_linha_db(nome_aba, patrimonio[tipo])
                logger.info(f"✅ Nova linha processada e enviada para o banco ({nome_aba}).")
            except Exception as e:
                logger.error(f"❌ Erro ao adicionar linha em {nome_aba} no Postgres: {e}")
                
def main():
    """Orquestrador do Pipeline de Dados (ETL)"""
    logger.info("=" * 70)
    logger.info("🚀 PIPELINE DE DADOS - CONTROLE FINANCEIRO")
    logger.info("=" * 70)

    # 1. EXTRACT (Extração)
    logger.info("Conectando às fontes de dados...")
    try:
        spreadsheet = conectar_google_sheets()
        loader = DataLoader(spreadsheet)
        dados = loader.carregar_todas_abas()
        logger.info("✅ Dados extraídos com sucesso.")
    except Exception as e:
        logger.critical(f"Falha fatal na extração: {e}")
        return

    # 2. TRANSFORM (Transformação e Lógica de Negócios)
    logger.info("Iniciando processamento das métricas...")
    
    # Processa o motor de Fluxo de Caixa
    processor = FluxoCaixaProcessor(dados=dados, mapa_pagamentos=dados['mapa_pagamentos'])
    df_master = processor.processar_todas_movimentacoes()
    
    # Processa o motor de Patrimônio
    patrimonio_calc = PatrimonioCalculator(dados['investimentos'])
    patrimonio = patrimonio_calc.processar_tudo()
    
    # Executa a limpeza fina
    df_master, patrimonio = limpar_dados(df_master, patrimonio)
    logger.info("✅ Dados processados e limpos.")

    # 3. LOAD (Carga)
    # Carrega no ambiente de UI/Backup
    sincronizar_google_sheets(spreadsheet, df_master, patrimonio)
    
    # Carrega no ambiente Analítico (BD)
    sincronizar_postgres(df_master, patrimonio)

    logger.info("=" * 70)
    logger.info("🏁 PROCESSAMENTO CONCLUÍDO COM SUCESSO")
    logger.info("=" * 70)

if __name__ == "__main__":
    main()