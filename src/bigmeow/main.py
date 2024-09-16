import asyncio
import signal
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from functools import partial
from typing import Any

import structlog
from dotenv import load_dotenv

import bigmeow.settings as settings
from bigmeow.discord import run as discord_run
from bigmeow.telegram import run as telegram_run
from bigmeow.web import run as web_run

load_dotenv()

logger = structlog.get_logger()


def done_handler(task: Future, exit_event: settings.Event) -> None:
    if task.exception() is not None:
        logger.exception(task.exception())

    shutdown_handler_threadpool(None, None, exit_event)


def shutdown_handler_threadpool(_signum, _frame, exit_event: settings.Event) -> None:
    logger.info("MAIN: Sending exit event")
    exit_event.set()


def threading_setup() -> None:
    settings.cat_lock = settings.Lock(threading.Lock())
    settings.fact_lock = settings.Lock(threading.Lock())
    settings.latest_lock = settings.Lock(threading.Lock())
    settings.telegram_updates = settings.Queue()

    settings.discord_messages = settings.Queue()
    settings.telegram_messages = settings.Queue()


def main() -> None:
    threading_setup()

    exit_event = settings.Event()

    with ThreadPoolExecutor(max_workers=10) as executor:
        for s in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
            signal.signal(
                s, partial(shutdown_handler_threadpool, exit_event=exit_event)
            )

        tasks = [
            executor.submit(lambda: asyncio.run(telegram_run(exit_event))),
            executor.submit(lambda: asyncio.run(discord_run(exit_event))),
        ]

        for task in tasks:
            task.add_done_callback(partial(done_handler, exit_event=exit_event))

        web_run()


if __name__ == "__main__":
    main()
