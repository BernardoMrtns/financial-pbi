"""Lançador único: roda o bot do Telegram e o do Discord no MESMO processo.

Este é o entrypoint do serviço na VM (ex.: systemd/cron). Cada bot expõe um
`run_async()` que integra ao event loop compartilhado — por isso NÃO usamos
`run_polling()`/`bot.run()` aqui (eles criariam loops próprios e conflitariam).

    python run_bots.py

Para rodar só um deles, use os módulos standalone:
    python -m bots.telegram_bot
    python -m bots.discord_bot
"""

import asyncio

from bots.discord_bot import run_async as discord_run
from bots.telegram_bot import run_async as telegram_run
from utils.logging_config import get_logger

logger = get_logger(__name__)


async def main() -> None:
    logger.info("Iniciando Telegram + Discord no mesmo processo...")
    # return_exceptions=False: se um bot morrer, propaga e o serviço reinicia.
    await asyncio.gather(telegram_run(), discord_run())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Encerrando os bots.")
