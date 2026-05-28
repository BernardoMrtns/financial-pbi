import pandas as pd
from processors import DataLoader, FluxoCaixaProcessor, PatrimonioCalculator
from services import conectar_google_sheets
from services.google_sheets import salvar_aba, adicionar_linha_aba
from services.database import atualizar_tabela_completa, adicionar_linha_db
from utils import get_logger

logger = get_logger(__name__)

def limpar_dados(df_master, patrimonio):
    """Padroniza e limpa os dados antes de enviar para os destinos."""
    logger.info("Realizando limpeza e tipagem dos dados...")
    
    if not df_master.empty:
        for col in ['DataOriginal', 'DataCompetencia']:
            if col in df_master.columns:
                df_master[col] = pd.to_datetime(df_master[col]).dt.strftime('%Y-%m-%d %H:%M:%S')
        for col in ['Valor', 'ValorFluxo']:
            if col in df_master.columns:
                df_master[col] = df_master[col].astype(float).round(2)

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

def sincronizar_postgres(df_master, patrimonio):
    """Abordagem focada em Data Warehouse: Prepara as tabelas para o Power BI."""
    logger.info("--- [1/2] Iniciando carga no Banco de Dados (Source of Truth) ---")
    
    if not df_master.empty:
        try:
            atualizar_tabela_completa("FluxoCaixaCompleto", df_master)
            logger.info("✅ Tabela 'fluxo_caixa' sobrescrita no Postgres.")
        except Exception as e:
            logger.error(f"❌ Erro ao atualizar fluxo_caixa no Postgres: {e}")

    tabelas_investimento = [('btc', 'InvestimentoBTC'), ('cdi', 'InvestimentoCDI'), ('cripto', 'InvestimentoCripto')]
    for tipo, nome_aba in tabelas_investimento:
        if not patrimonio[tipo].empty:
            try:
                adicionar_linha_db(nome_aba, patrimonio[tipo])
                logger.info(f"✅ Novas linhas de {nome_aba} processadas e enviadas para o Postgres.")
            except Exception as e:
                logger.error(f"❌ Erro ao adicionar linha em {nome_aba} no Postgres: {e}")

def sincronizar_google_sheets_backup(df_master, patrimonio):
    """Abordagem focada em Backup/UI visual no celular. Isolado para não quebrar o pipeline principal."""
    logger.info("--- [2/2] Iniciando espelhamento no Google Sheets (Backup Visual) ---")
    try:
        # A conexão só ocorre aqui. Se falhar, é isolada no try-except
        spreadsheet = conectar_google_sheets()
        
        if not df_master.empty:
            salvar_aba(spreadsheet, "FluxoCaixaCompleto", df_master)
            logger.info("✅ Planilha 'FluxoCaixaCompleto' espelhada com sucesso.")

        abas_investimento = [('btc', 'InvestimentoBTC'), ('cdi', 'InvestimentoCDI'), ('cripto', 'InvestimentoCripto')]
        for tipo, nome_aba in abas_investimento:
            if not patrimonio[tipo].empty:
                adicionar_linha_aba(spreadsheet, nome_aba, patrimonio[tipo])
                logger.info(f"✅ Nova linha espelhada na aba '{nome_aba}'.")

    except Exception as e:
        logger.warning(f"⚠️ Ocorreu um erro ao espelhar no Sheets (o DB está seguro): {e}")

def main():
    """Orquestrador do Pipeline de Dados (ETL) Desacoplado"""
    logger.info("=" * 70)
    logger.info("🚀 PIPELINE DE DADOS (DB-FIRST) - CONTROLE FINANCEIRO")
    logger.info("=" * 70)

    # 1. EXTRACT (Do banco de dados)
    try:
        loader = DataLoader()
        dados = loader.carregar_todas_abas()
        logger.info("✅ Dados extraídos do banco de dados com sucesso.")
    except Exception as e:
        logger.critical(f"Falha fatal na extração do PostgreSQL: {e}")
        return

    # 2. TRANSFORM (Geração do Dataframe Mestre de Fluxo e Patrimônio)
    logger.info("Iniciando processamento das métricas...")
    processor = FluxoCaixaProcessor(dados=dados, mapa_pagamentos=dados.get('mapa_pagamentos', {}))
    df_master = processor.processar_todas_movimentacoes()
    
    patrimonio_calc = PatrimonioCalculator(dados.get('investimentos', pd.DataFrame()))
    patrimonio = patrimonio_calc.processar_tudo()
    
    df_master, patrimonio = limpar_dados(df_master, patrimonio)
    logger.info("✅ Dados processados e limpos.")

    # 3. LOAD CORE (Salva o resultado no PostgreSQL)
    sincronizar_postgres(df_master, patrimonio)
    
    # 4. LOAD VISUAL (Tenta replicar no Sheets para conferência mobile)
    sincronizar_google_sheets_backup(df_master, patrimonio)

    logger.info("=" * 70)
    logger.info("🏁 PROCESSAMENTO CONCLUÍDO")
    logger.info("=" * 70)

if __name__ == "__main__":
    main()