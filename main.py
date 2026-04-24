from processors import DataLoader, FluxoCaixaProcessor, PatrimonioCalculator
from services import adicionar_linha_aba, conectar_google_sheets, salvar_aba
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

    # 5. Salva resultados
    logger.info("Salvando no Google Sheets")

    if not df_master.empty:
        salvar_aba(spreadsheet, "FluxoCaixaCompleto", df_master)
        logger.info("FluxoCaixaCompleto salvo")

    if not patrimonio['btc'].empty:
        adicionar_linha_aba(spreadsheet, "InvestimentoBTC", patrimonio['btc'])
        logger.info("Nova linha adicionada em InvestimentoBTC")

    if not patrimonio['cdi'].empty:
        adicionar_linha_aba(spreadsheet, "InvestimentoCDI", patrimonio['cdi'])
        logger.info("Nova linha adicionada em InvestimentoCDI")

    if not patrimonio['cripto'].empty:
        adicionar_linha_aba(spreadsheet, "InvestimentoCripto", patrimonio['cripto'])
        logger.info("Nova linha adicionada em InvestimentoCripto")

    logger.info("%s", "=" * 70)
    logger.info("PROCESSAMENTO CONCLUIDO COM SUCESSO")
    logger.info("%s", "=" * 70)


if __name__ == "__main__":
    main()
