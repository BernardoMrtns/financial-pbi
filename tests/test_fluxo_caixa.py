import pandas as pd

from processors.fluxo_caixa import FluxoCaixaProcessor


def _empty_df(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def test_fluxo_caixa_cartao_status_and_valor_fluxo() -> None:
    dados = {
        "compras": pd.DataFrame(
            [
                {
                    "Data": pd.Timestamp("2026-04-01"),
                    "Descricao": "Notebook",
                    "Categoria": "Tecnologia",
                    "Cartao": "Inter",
                    "ValorTotal": 100.0,
                    "Parcelas": 2,
                }
            ]
        ),
        "pix": _empty_df(["Data", "Descricao", "Categoria", "ValorTotal", "ValorEntrada", "QtdPagas"]),
        "assinaturas": _empty_df(["Nome", "Categoria", "Valor", "DiaCobranca", "Cartao", "Ativa", "Inicio", "Fim"]),
        "debitos": _empty_df(["Data", "Descricao", "Categoria", "Valor", "ContaSaida"]),
        "receitas": _empty_df(["Data", "Descricao", "Categoria", "Valor", "ContaDestino"]),
        "investimentos": _empty_df(["Data", "Tipo", "Operacao", "Valor", "Quantidade", "QuantidadeBTC"]),
    }
    mapa_pagamentos = {"Inter": pd.Timestamp("2026-04-01")}

    processor = FluxoCaixaProcessor(dados=dados, mapa_pagamentos=mapa_pagamentos)
    resultado = processor.processar_todas_movimentacoes()

    assert len(resultado) == 2
    assert set(resultado["Status"].tolist()) == {"Pago", "Pendente"}
    assert resultado["ValorFluxo"].sum() == -100.0
