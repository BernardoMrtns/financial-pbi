"""Constantes de dominio compartilhadas por Views, Modals e Slash Commands.

Espelham as enums usadas pelo parser de IA (services/ai_parser.py) para que a UI
manual produza exatamente os mesmos valores canonicos que a IA geraria.
"""

from __future__ import annotations

import discord

# --- Valores canonicos (devem bater com o schema do ai_parser) ---

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

CARTOES: list[str] = ["Inter", "Nubank", "MercadoPago", "PicPay", "AmazonPrime"]

# Contas usadas para debito/receita (inclui dinheiro fisico, alem dos cartoes).
CONTAS: list[str] = ["Inter", "Nubank", "MercadoPago", "PicPay", "Dinheiro"]

PRIORIDADES: list[str] = ["Baixa", "Media", "Alta"]

CATEGORIA_PADRAO = "Outros"
CONTA_PADRAO = "Inter"
PRIORIDADE_PADRAO = "Media"


# --- Identidade visual do painel (cor + emoji por tipo de operacao) ---

COR_RECEITA = discord.Color.from_str("#2ecc71")
COR_DEBITO = discord.Color.from_str("#e74c3c")
COR_CARTAO = discord.Color.from_str("#9b59b6")
COR_PIX = discord.Color.from_str("#1abc9c")
COR_ASSINATURA = discord.Color.from_str("#e67e22")
COR_ERRO = discord.Color.from_str("#992d22")
COR_PAINEL = discord.Color.from_str("#5865f2")
