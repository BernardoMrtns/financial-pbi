from modules import (
    conectar_google_sheets,
    salvar_aba,
    adicionar_linha_aba,
    DataLoader,
    FluxoCaixaProcessor,
    PatrimonioCalculator
)


def main():
    """
    Função principal que executa todo o fluxo de processamento
    """
    print("=" * 70)
    print("SISTEMA DE CONTROLE FINANCEIRO")
    print("=" * 70)

    # 1. Conecta ao Google Sheets
    print("\n🔗 Conectando ao Google Sheets...")
    spreadsheet = conectar_google_sheets()
    print("✅ Conectado com sucesso!")

    # 2. Carrega todos os dados
    loader = DataLoader(spreadsheet)
    dados = loader.carregar_todas_abas()
    print("✅ Dados carregados!")

    # 3. Processa fluxo de caixa
    processor = FluxoCaixaProcessor(
        dados=dados,
        mapa_pagamentos=dados['mapa_pagamentos']
    )
    df_master = processor.processar_todas_movimentacoes()
    print("✅ Fluxo de caixa processado!")

    # 4. Calcula patrimônio
    patrimonio_calc = PatrimonioCalculator(dados['investimentos'])
    patrimonio = patrimonio_calc.processar_tudo()
    print("✅ Patrimônio calculado!")

    # 5. Salva resultados
    print("\n💾 Salvando no Google Sheets...")

    if not df_master.empty:
        salvar_aba(spreadsheet, "FluxoCaixaCompleto", df_master)
        print("  ✓ FluxoCaixaCompleto salvo")

    if not patrimonio['btc'].empty:
        adicionar_linha_aba(spreadsheet, "InvestimentoBTC", patrimonio['btc'])
        print("  ✓ Nova linha adicionada em InvestimentoBTC")

    if not patrimonio['cdi'].empty:
        salvar_aba(spreadsheet, "InvestimentoCDI", patrimonio['cdi'])
        print("  ✓ InvestimentoCDI salvo")

    if not patrimonio['cripto'].empty:
        adicionar_linha_aba(spreadsheet, "InvestimentoCripto", patrimonio['cripto'])
        print("  ✓ Nova linha adicionada em InvestimentoCripto")

    print("\n" + "=" * 70)
    print("✅ PROCESSAMENTO CONCLUÍDO COM SUCESSO!")
    print("=" * 70)


if __name__ == "__main__":
    main()
