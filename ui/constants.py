"""Constantes de dominio compartilhadas por Views, Modals e Slash Commands.

Espelham as enums usadas pelo parser de IA (services/ai_parser.py) para que a UI
manual produza exatamente os mesmos valores canonicos que a IA geraria.
"""

from __future__ import annotations

import discord

# --- Valores canonicos (devem bater com o schema do ai_parser) ---

# Categorias de saida (compras/debitos/cartao/pix/wishlist/assinaturas).
CATEGORIAS: list[str] = [
    "Vestuário",
    "Comida",
    "iFood",
    "Lazer",
    "Saúde",
    "Presentes",
    "Utilidades",
    "Eletrônicos",
    "Moradia",
    "Transporte",
    "Educação",
    "Assinaturas",
    "Viagem",
    "Bebidas",
    "Outros",
]

# Categorias de entrada (receitas) — vocabulario proprio, distinto das compras.
CATEGORIAS_RECEITA: list[str] = [
    "Trabalho",
    "Pix Avulso",
]

CARTOES: list[str] = ["Inter", "Nubank", "MercadoPago", "PicPay", "AmazonPrime"]

# Contas usadas para debito/receita (inclui dinheiro fisico, alem dos cartoes).
CONTAS: list[str] = ["Inter", "Nubank", "MercadoPago", "PicPay", "Dinheiro"]

PRIORIDADES: list[str] = ["Baixa", "Media", "Alta"]

# Periodicidade de cobranca das assinaturas. O ETL traduz para um intervalo em
# meses (MESES_POR_PERIODICIDADE em processors/fluxo_caixa.py).
PERIODICIDADES: list[str] = ["Mensal", "Anual"]

# Classe do ativo em Investimentos. Discrimina o roteamento de cotacao no ETL:
# CDI acumula pela serie do Bacen, Cripto consulta a CoinGecko, ETF/Acao a brapi.
# O ticker em si continua na coluna Tipo (BTC, ETH, BOVA11, PETR4).
CLASSES_INVESTIMENTO: list[str] = ["CDI", "Cripto", "ETF", "Acao"]

OPERACOES_INVESTIMENTO: list[str] = ["Aporte", "Saque"]

CATEGORIA_PADRAO = "Outros"
CATEGORIA_RECEITA_PADRAO = "Pix Avulso"
CONTA_PADRAO = "Inter"
PRIORIDADE_PADRAO = "Media"
PERIODICIDADE_PADRAO = "Mensal"
CLASSE_INVESTIMENTO_PADRAO = "Cripto"
OPERACAO_INVESTIMENTO_PADRAO = "Aporte"


# --- Identidade visual do painel (cor + emoji por tipo de operacao) ---

COR_RECEITA = discord.Color.from_str("#059669")  # Emerald-600 (darker)
COR_DEBITO = discord.Color.from_str("#dc2626")  # Red-600
COR_CARTAO = discord.Color.from_str("#6d28d9")  # Violet-700 (muted purple)
COR_PIX = discord.Color.from_str("#0d9488")     # Teal-600
COR_ASSINATURA = discord.Color.from_str("#d97706")  # Amber-600
COR_ERRO = discord.Color.from_str("#b91c1c")   # Red-700 (error)
COR_PAINEL = discord.Color.from_str("#0f172a")  # Slate-900 (dark panel)
