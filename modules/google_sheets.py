"""Compatibility shim for legacy import path modules.google_sheets."""

from services.google_sheets import adicionar_linha_aba, carregar_aba, conectar_google_sheets, salvar_aba

__all__ = ["conectar_google_sheets", "carregar_aba", "salvar_aba", "adicionar_linha_aba"]
