"""Cotacoes de renda variavel na B3 (ETFs e acoes) via Yahoo Finance.

Escolhido por ser a unica fonte gratuita que cobre ETFs da B3: a brapi.dev
passou a cobrar (~R$100/mes) e libera de graca apenas quatro acoes em sandbox,
sem nenhum ETF.

Ressalva: o endpoint e publico mas nao documentado, entao pode mudar sem aviso.
Se um dia parar de responder, todo ticker cai como "sem cotacao", a renda
variavel e pulada e o resto do patrimonio (CDI, BTC, cripto) segue intacto.

O endpoint de lote (v7/finance/quote) exige cookie e crumb, entao aqui e uma
requisicao por ticker -- o que e irrelevante no volume deste projeto (poucos
ativos, uma vez por hora).
"""

from __future__ import annotations

from typing import Any

import requests
from requests import RequestException

from config import REQUEST_TIMEOUT_SECONDS, YAHOO_QUOTE_URL
from utils.logging_config import get_logger
from utils.retry import retry_call

logger = get_logger(__name__)

# Ativos da B3 no Yahoo levam o sufixo do pais.
SUFIXO_B3 = ".SA"

# O Yahoo recusa o User-Agent padrao das bibliotecas HTTP.
CABECALHOS = {"User-Agent": "Mozilla/5.0 (compatible; financial-pbi/1.0)"}


def _simbolo_yahoo(ticker: str) -> str:
    limpo = str(ticker).upper().strip()
    return limpo if limpo.endswith(SUFIXO_B3) else limpo + SUFIXO_B3


def _cotacao_de(ticker: str) -> dict[str, Any] | None:
    """Cotacao atual de um ticker, ou None se o Yahoo nao reconhecer."""
    simbolo = _simbolo_yahoo(ticker)

    def fetch() -> dict[str, Any]:
        response = requests.get(
            f"{YAHOO_QUOTE_URL}/{simbolo}",
            params={"interval": "1d", "range": "1d"},
            headers=CABECALHOS,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()

    try:
        payload = retry_call(fetch, (RequestException,), f"cotacao {simbolo}")
    except RuntimeError as error:
        logger.warning("Falha ao consultar %s: %s", simbolo, error)
        return None

    try:
        meta = payload["chart"]["result"][0]["meta"]
    except (KeyError, IndexError, TypeError):
        return None

    preco = meta.get("regularMarketPrice")
    if not preco:
        return None

    if meta.get("currency") != "BRL":
        # Sem conversao cambial no pipeline: somar em outra moeda distorceria o
        # PatrimonioTotal em silencio.
        logger.warning(
            "%s cotado em %s, nao em BRL; ignorado.", simbolo, meta.get("currency")
        )
        return None

    nome = meta.get("longName") or meta.get("shortName") or ticker
    return {"preco": float(preco), "nome": str(nome)}


def buscar_cotacoes(tickers: list[str]) -> dict[str, dict[str, Any]]:
    """Cotacao atual em BRL de uma lista de tickers da B3.

    Retorna {TICKER: {"preco": float, "nome": str}} usando o ticker como o
    chamador escreveu (sem o sufixo .SA). Tickers nao reconhecidos ficam de
    fora do resultado.
    """
    limpos = sorted({str(t).upper().strip() for t in tickers if str(t).strip()})
    if not limpos:
        return {}

    cotacoes: dict[str, dict[str, Any]] = {}
    for ticker in limpos:
        cotacao = _cotacao_de(ticker)
        if cotacao:
            cotacoes[ticker] = cotacao

    nao_resolvidos = [t for t in limpos if t not in cotacoes]
    if nao_resolvidos:
        logger.warning("Tickers sem cotacao na B3: %s", ", ".join(nao_resolvidos))

    return cotacoes
