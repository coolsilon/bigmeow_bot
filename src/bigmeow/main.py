import asyncio
import signal
from functools import partial
from typing import Any

import structlog
from dotenv import load_dotenv

from bigmeow.discord import run as discord_run
from bigmeow.telegram import run as telegram_run
from bigmeow.web import run as web_run

load_dotenv()

logger = structlog.get_logger()


def exception_handler(
    loop: asyncio.AbstractEventLoop, context: dict[str, Any], exit_event: asyncio.Event
) -> None:
    message = context.get("exception", context["message"])
    logger.error("Caught exception", message=message)

    logger.error("MAIN: Shutting down")
    asyncio.create_task(shutdown_handler(loop, exit_event))


async def shutdown_handler(
    loop: asyncio.AbstractEventLoop, exit_event: asyncio.Event
) -> None:
    logger.info("MAIN: Sending exit event")
    exit_event.set()

    await asyncio.sleep(5)

    tasks = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]

    for task in tasks:
        task.cancel()

    await asyncio.gather(*tasks, return_exceptions=True)

    loop.stop()


def main() -> None:
    loop, exit_event = asyncio.get_event_loop(), asyncio.Event()

    loop.set_exception_handler(partial(exception_handler, exit_event=exit_event))

    for s in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            s,
            lambda: asyncio.create_task(shutdown_handler(loop, exit_event)),
        )

    try:
        loop.create_task(telegram_run(exit_event))
        loop.create_task(discord_run(exit_event))
        loop.create_task(web_run(exit_event))
        loop.run_forever()
    finally:
        loop.close()


if __name__ == "__main__":
    main()
