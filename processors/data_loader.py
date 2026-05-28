from __future__ import annotations
from typing import Any, Dict
import pandas as pd

from config import SCHEMA_ABAS
from services.database import ler_tabela_db
from utils import converter_data_flexivel, converter_numero_flexivel, get_logger, normalizar_nome_cartao

logger = get_logger(__name__)

# Mapa para converter o padrão snake_case do Postgres de volta para o padrão esperado em memória
RENOMEIOS_DB_PARA_MEMORIA = {
    'data': 'Data', 'descricao': 'Descricao', 'categoria': 'Categoria',
    'cartao': 'Cartao', 'valor_total': 'ValorTotal', 'parcelas': 'Parcelas',
    'valor': 'Valor', 'dia_cobranca': 'DiaCobranca', 'ativa': 'Ativa',
    'inicio': 'Inicio', 'fim': 'Fim', 'nome': 'Nome',
    'valor_entrada': 'ValorEntrada', 'qtd_pagas': 'QtdPagas',
    'conta_destino': 'ContaDestino', 'conta_saida': 'ContaSaida',
    'data_hora': 'DataHora', 'operacao': 'Operacao', 'tipo': 'Tipo',
    'preco': 'Preco', 'ultimo_ciclo_pago': 'UltimoCicloPago',
    'quantidade': 'Quantidade',
    'quantidade_cripto': 'QuantidadeCripto'
}

class DataLoader:
    def __init__(self):
        # Independente do Sheets. Inicia vazio.
        pass

    def _carregar_e_padronizar(self, nome_aba: str) -> pd.DataFrame:
        """Lê do banco e renomeia as colunas para evitar quebra no processador."""
        df = ler_tabela_db(nome_aba)
        if not df.empty:
            df = df.rename(columns=RENOMEIOS_DB_PARA_MEMORIA)
        return df

    def carregar_todas_abas(self) -> Dict[str, Any]:
        logger.info("Extraindo dados brutos do PostgreSQL...")

        df_fpg = self._carregar_e_padronizar("FaturasPagas")
        df_compras = self._carregar_e_padronizar("ComprasCartao")
        df_pix = self._carregar_e_padronizar("PixParcelado")
        df_assin = self._carregar_e_padronizar("Assinaturas")
        df_debito = self._carregar_e_padronizar("DebitoAvulso")
        df_receitas = self._carregar_e_padronizar("Receitas")
        df_inv = self._carregar_e_padronizar("Investimentos")

        # Processamento de datas para o mapa de pagamentos
        mapa_pagamentos = {}
        if not df_fpg.empty and "UltimoCicloPago" in df_fpg.columns:
            df_fpg["UltimoCicloPago"] = converter_data_flexivel(df_fpg["UltimoCicloPago"]).dt.to_period("M").dt.to_timestamp()
            mapa_pagamentos = dict(zip(df_fpg["Cartao"].map(normalizar_nome_cartao), df_fpg["UltimoCicloPago"]))

        # Limpeza e tipagem dos DataFrames extraídos do DB
        for df in [df_compras, df_pix, df_assin, df_debito, df_receitas]:
            if df.empty:
                continue
            if "Data" in df.columns:
                df["Data"] = converter_data_flexivel(df["Data"])
            if "Inicio" in df.columns:
                df["Inicio"] = converter_data_flexivel(df["Inicio"])
            if "Fim" in df.columns:
                df["Fim"] = converter_data_flexivel(df["Fim"])
            if "ValorTotal" in df.columns:
                df["ValorTotal"] = converter_numero_flexivel(df["ValorTotal"])
            if "Valor" in df.columns:
                df["Valor"] = converter_numero_flexivel(df["Valor"])

        if not df_inv.empty:
            if "DataHora" in df_inv.columns:
                df_inv["DataHora"] = converter_data_flexivel(df_inv["DataHora"], preservar_hora=True)
            elif "Data" in df_inv.columns:
                df_inv["Data"] = converter_data_flexivel(df_inv["Data"], preservar_hora=True)
            if "Valor" in df_inv.columns:
                df_inv["Valor"] = converter_numero_flexivel(df_inv["Valor"])

        return {
            "mapa_pagamentos": mapa_pagamentos,
            "compras": df_compras,
            "pix": df_pix,
            "assinaturas": df_assin,
            "debitos": df_debito,
            "receitas": df_receitas,
            "investimentos": df_inv,
        }