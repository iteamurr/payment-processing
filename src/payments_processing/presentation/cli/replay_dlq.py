"""Moves dead-lettered payments.new messages back for processing.

Run: python -m payments_processing.presentation.cli.replay_dlq
"""

import asyncio
import logging

from faststream.rabbit import RabbitBroker

from payments_processing.infrastructure.broker.dlq import replay_dead_letters
from payments_processing.project.container import get_consumer_container
from payments_processing.project.logging import configure_logging


async def main() -> None:
    configure_logging()
    broker = get_consumer_container().resolve(RabbitBroker)
    await broker.connect()
    try:
        replayed = await replay_dead_letters(broker)
    finally:
        await broker.stop()
    logging.getLogger(__name__).info("replayed %s dead-lettered messages", replayed)


if __name__ == "__main__":
    asyncio.run(main())
