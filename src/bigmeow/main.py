import asyncio
import os
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
        logger.error(str(task.exception()))

    shutdown_handler_threadpool(None, None, exit_event)


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

def shutdown_handler_threadpool(_signum, _frame, exit_event: settings.Event) -> None:
    logger.info("MAIN: Sending exit event")
    exit_event.set()


def threading_setup():
    settings.cat_lock = settings.Lock(threading.Lock())
    settings.fact_lock = settings.Lock(threading.Lock())
    settings.latest_lock = settings.Lock(threading.Lock())
    settings.telegram_queue = settings.Queue()


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


def main_threadpool() -> None:
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
            executor.submit(lambda: asyncio.run(web_run(exit_event))),
        ]

        for task in tasks:
            task.add_done_callback(partial(done_handler, exit_event=exit_event))


if __name__ == "__main__":
    if os.environ.get("MEOW_THREADS", "False").upper() == "TRUE":
        main_threadpool()
    else:
        main()
