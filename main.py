import pandas as pd
from processors import DataLoader, FluxoCaixaProcessor, PatrimonioCalculator
from services import adicionar_linha_aba, conectar_google_sheets, salvar_aba
from services.database import atualizar_tabela_completa, adicionar_linha_db
from utils import get_logger

logger = get_logger(__name__)


def main():
    """
    Função principal que executa todo o fluxo de processamento
    """
    logger.info("%s", "=" * 70)
    logger.info("SISTEMA DE CONTROLE FINANCEIRO")
    logger.info("%s", "=" * 70)

    # 1. Conecta ao Google Sheets
    logger.info("Conectando ao Google Sheets")
    spreadsheet = conectar_google_sheets()
    logger.info("Conectado com sucesso")

    # 2. Carrega todos os dados
    loader = DataLoader(spreadsheet)
    dados = loader.carregar_todas_abas()
    logger.info("Dados carregados")

    # 3. Processa fluxo de caixa
    processor = FluxoCaixaProcessor(
        dados=dados,
        mapa_pagamentos=dados['mapa_pagamentos']
    )
    df_master = processor.processar_todas_movimentacoes()
    logger.info("Fluxo de caixa processado")

    # 4. Calcula patrimônio
    patrimonio_calc = PatrimonioCalculator(dados['investimentos'])
    patrimonio = patrimonio_calc.processar_tudo()
    logger.info("Patrimonio calculado")

    # === LIMPEZA E PADRONIZAÇÃO DOS DADOS ANTES DE SALVAR ===
    # -> 1. LIMPEZA DO FLUXO DE CAIXA
    if not df_master.empty:
        # Formata datas removendo os microssegundos
        for col in ['DataOriginal', 'DataCompetencia']:
            if col in df_master.columns:
                df_master[col] = pd.to_datetime(df_master[col]).dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # Arredonda valores para 2 casas decimais
        for col in ['Valor', 'ValorFluxo']:
            if col in df_master.columns:
                df_master[col] = df_master[col].astype(float).round(2)

    # -> 2. LIMPEZA DO PATRIMÔNIO (Investimentos)
    for tipo in ['btc', 'cdi', 'cripto']:
        if not patrimonio[tipo].empty:
            df = patrimonio[tipo]
            
            # Remove os microssegundos da Data
            if 'DataHora' in df.columns:
                df['DataHora'] = pd.to_datetime(df['DataHora']).dt.strftime('%Y-%m-%d %H:%M:%S')
            
            # Arredonda valores de Moeda Fiduciária (R$)
            for col in ['ValorCDI', 'PrecoBTC', 'ValorReais', 'PrecoCripto']:
                if col in df.columns:
                    df[col] = df[col].astype(float).round(2)
            
            # Arredonda saldos de Criptomoedas
            for col in ['SaldoBTC', 'SaldoCripto']:
                if col in df.columns:
                    df[col] = df[col].astype(float).round(8)
    # ==============================================================

    # 5. Salva resultados
    logger.info("Salvando no Google Sheets")

    if not df_master.empty:
        salvar_aba(spreadsheet, "FluxoCaixaCompleto", df_master)
        logger.info("FluxoCaixaCompleto salvo")
        try:
            atualizar_tabela_completa("FluxoCaixaCompleto", df_master)
        except Exception:
            # A função já loga internamente, garantir que falhas no DB não parem o fluxo
            logger.exception("Falha ao atualizar tabela FluxoCaixaCompleto no PostgreSQL")

    if not patrimonio['btc'].empty:
        adicionar_linha_aba(spreadsheet, "InvestimentoBTC", patrimonio['btc'])
        logger.info("Nova linha adicionada em InvestimentoBTC")
        try:
            adicionar_linha_db("InvestimentoBTC", patrimonio['btc'])
        except Exception:
            logger.exception("Falha ao adicionar linha InvestimentoBTC no PostgreSQL")

    if not patrimonio['cdi'].empty:
        adicionar_linha_aba(spreadsheet, "InvestimentoCDI", patrimonio['cdi'])
        logger.info("Nova linha adicionada em InvestimentoCDI")
        try:
            adicionar_linha_db("InvestimentoCDI", patrimonio['cdi'])
        except Exception:
            logger.exception("Falha ao adicionar linha InvestimentoCDI no PostgreSQL")

    if not patrimonio['cripto'].empty:
        adicionar_linha_aba(spreadsheet, "InvestimentoCripto", patrimonio['cripto'])
        logger.info("Nova linha adicionada em InvestimentoCripto")
        try:
            adicionar_linha_db("InvestimentoCripto", patrimonio['cripto'])
        except Exception:
            logger.exception("Falha ao adicionar linha InvestimentoCripto no PostgreSQL")

    logger.info("%s", "=" * 70)
    logger.info("PROCESSAMENTO CONCLUIDO COM SUCESSO")
    logger.info("%s", "=" * 70)


if __name__ == "__main__":
    main()