import pandas as pd

from models.finance import Movimentacao


def test_movimentacao_to_dict() -> None:
    movimentacao = Movimentacao(
        data_original=pd.Timestamp("2026-04-01"),
        data_competencia=pd.Timestamp("2026-04-01"),
        tipo="Saida",
        metodo="Cartao",
        conta_cartao="Inter",
        categoria="Compras",
        descricao="Teste",
        valor=100.0,
        status="Pago",
    )

    payload = movimentacao.to_dict()

    assert payload["Tipo"] == "Saida"
    assert payload["Valor"] == 100.0
    assert payload["Conta_Cartao"] == "Inter"
