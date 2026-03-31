"""
Módulo para carregamento e normalização de dados das abas
"""
import pandas as pd
from modules.google_sheets import carregar_aba
from modules.utils import converter_data_flexivel, converter_numero_flexivel
from config import SCHEMA_ABAS


class DataLoader:
    """
    Responsável por carregar todas as abas do Google Sheets
    e normalizar os dados
    """

    def __init__(self, spreadsheet):
        self.spreadsheet = spreadsheet

    def carregar_todas_abas(self):
        """
        Carrega todas as abas necessárias e retorna um dicionário com os dados
        """
        print("📂 Lendo abas do Google Sheets...")

        # Carrega FaturasPagas
        df_fpg = carregar_aba(self.spreadsheet, "FaturasPagas", SCHEMA_ABAS["FaturasPagas"])
        df_fpg["UltimoCicloPago"] = converter_data_flexivel(df_fpg["UltimoCicloPago"]).dt.to_period("M").dt.to_timestamp()
        mapa_pagamentos = dict(zip(df_fpg["Cartao"], df_fpg["UltimoCicloPago"]))

        # Carrega demais abas
        df_compras = carregar_aba(self.spreadsheet, "ComprasCartao", SCHEMA_ABAS["ComprasCartao"])
        df_pix = carregar_aba(self.spreadsheet, "PixParcelado", SCHEMA_ABAS["PixParcelado"])
        df_assin = carregar_aba(self.spreadsheet, "Assinaturas", SCHEMA_ABAS["Assinaturas"])
        df_debito = carregar_aba(self.spreadsheet, "DebitoAvulso", SCHEMA_ABAS["DebitoAvulso"])
        df_receitas = carregar_aba(self.spreadsheet, "Receitas", SCHEMA_ABAS["Receitas"])
        df_inv = carregar_aba(self.spreadsheet, "Investimentos", SCHEMA_ABAS["Investimentos"])

        # Normalização geral - processa todas as tabelas exceto Investimentos
        tabelas = [df_compras, df_pix, df_assin, df_debito, df_receitas]
        for df in tabelas:
            # Aplica a conversão flexível corrigida (sem hora)
            if "Data" in df.columns:
                df["Data"] = converter_data_flexivel(df["Data"])
            if "Inicio" in df.columns:
                df["Inicio"] = converter_data_flexivel(df["Inicio"])
            if "Fim" in df.columns:
                df["Fim"] = converter_data_flexivel(df["Fim"])

            # Tratamento de valores numéricos
            if "ValorTotal" in df.columns:
                df["ValorTotal"] = converter_numero_flexivel(df["ValorTotal"])
            if "Valor" in df.columns:
                df["Valor"] = converter_numero_flexivel(df["Valor"])
        
        # Para Investimentos, preserva hora na coluna Data para precisão em cripto
        if "Data" in df_inv.columns:
            df_inv["Data"] = converter_data_flexivel(df_inv["Data"], preservar_hora=True)
        if "Valor" in df_inv.columns:
            df_inv["Valor"] = converter_numero_flexivel(df_inv["Valor"])

        return {
            'mapa_pagamentos': mapa_pagamentos,
            'compras': df_compras,
            'pix': df_pix,
            'assinaturas': df_assin,
            'debitos': df_debito,
            'receitas': df_receitas,
            'investimentos': df_inv
        }