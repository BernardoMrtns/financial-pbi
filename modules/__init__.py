"""Compatibility exports for legacy imports from modules."""

from processors import DataLoader, FluxoCaixaProcessor, PatrimonioCalculator
from services import adicionar_linha_aba, carregar_aba, conectar_google_sheets, salvar_aba
from utils import (
    calcular_fator_cdi_periodo,
    calcular_mes_competencia,
    converter_data_flexivel,
    obter_cdi_historico,
)

__all__ = [
    "conectar_google_sheets",
    "carregar_aba",
    "salvar_aba",
    "adicionar_linha_aba",
    "DataLoader",
    "FluxoCaixaProcessor",
    "PatrimonioCalculator",
    "converter_data_flexivel",
    "calcular_mes_competencia",
    "obter_cdi_historico",
    "calcular_fator_cdi_periodo",
]