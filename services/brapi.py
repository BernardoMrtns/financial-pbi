"""Cotacoes de renda variavel na B3 (ETFs e acoes) via brapi.dev.

Espelha a estrutura usada para cripto em processors/patrimonio.py: uma unica
chamada em lote por rodada de ETL, com retry e degradacao silenciosa quando um
ticker nao resolve.
"""

from __future__ import annotations

from typing import Any

import requests
from requests import RequestException

from config import BRAPI_QUOTE_URL, BRAPI_TOKEN, REQUEST_TIMEOUT_SECONDS
from utils.logging_config import get_logger
from utils.retry import retry_call

logger = get_logger(__name__)


def token_configurado() -> bool:
    """A brapi exige token mesmo no plano gratuito."""
    return bool(str(BRAPI_TOKEN).strip())


def buscar_cotacoes(tickers: list[str]) -> dict[str, dict[str, Any]]:
    """Cotacao atual em BRL de uma lista de tickers da B3.

    Retorna {TICKER: {"preco": float, "nome": str}}. Tickers que a API nao
    reconhecer simplesmente nao aparecem no resultado.
    """
    limpos = sorted({str(t).upper().strip() for t in tickers if str(t).strip()})
    if not limpos:
        return {}

    if not token_configurado():
        logger.warning(
            "BRAPI_TOKEN nao configurado; cotacao de renda variavel ignorada para: %s",
            ", ".join(limpos),
        )
        return {}

    url = f"{BRAPI_QUOTE_URL}/{','.join(limpos)}"

    try:
        def fetch() -> dict[str, Any]:
            response = requests.get(
                url,
                params={"token": BRAPI_TOKEN},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.json()

        payload = retry_call(fetch, (RequestException,), "consulta de cotacoes brapi")
    except RuntimeError as error:
        logger.error("Erro ao buscar cotacoes na brapi: %s", error)
        return {}

    cotacoes: dict[str, dict[str, Any]] = {}
    for resultado in payload.get("results", []) or []:
        ticker = str(resultado.get("symbol", "")).upper().strip()
        preco = resultado.get("regularMarketPrice")
        if not ticker or not preco:
            continue
        nome = resultado.get("longName") or resultado.get("shortName") or ticker
        cotacoes[ticker] = {"preco": float(preco), "nome": str(nome)}

    nao_resolvidos = [t for t in limpos if t not in cotacoes]
    if nao_resolvidos:
        logger.warning("Tickers sem cotacao na brapi: %s", ", ".join(nao_resolvidos))

    return cotacoes
