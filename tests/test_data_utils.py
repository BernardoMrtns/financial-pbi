import pandas as pd

from utils.data_utils import calcular_mes_competencia, converter_data_flexivel, converter_numero_flexivel


def test_converter_numero_flexivel_multiformato() -> None:
    serie = pd.Series(["1.234,56", "0,00092054", "370436.00", "", None])
    resultado = converter_numero_flexivel(serie)

    assert resultado.tolist() == [1234.56, 0.00092054, 370436.0, 0.0, 0.0]


def test_converter_data_flexivel_excel_serial() -> None:
    serie = pd.Series([45292, "01/01/2024", "16:24:00:00", ""])
    resultado = converter_data_flexivel(serie)

    assert resultado.iloc[0] == pd.Timestamp("2024-01-01")
    assert resultado.iloc[1] == pd.Timestamp("2024-01-01")
    assert pd.isna(resultado.iloc[2])
    assert pd.isna(resultado.iloc[3])


def test_calcular_mes_competencia() -> None:
    compra_antes_fechamento = pd.Timestamp("2026-04-07")
    compra_apos_fechamento = pd.Timestamp("2026-04-10")

    assert calcular_mes_competencia(compra_antes_fechamento, "Inter") == pd.Timestamp("2026-04-01")
    assert calcular_mes_competencia(compra_apos_fechamento, "Inter") == pd.Timestamp("2026-05-01")
