import asyncio
import multiprocessing
import signal
import threading
from concurrent.futures import Future, ProcessPoolExecutor, ThreadPoolExecutor
from functools import partial

import structlog
from dotenv import load_dotenv

import bigmeow.settings as settings
from bigmeow.discord import run as discord_run
from bigmeow.telegram import run as telegram_run
from bigmeow.web import run as web_run

load_dotenv()

logger = structlog.get_logger()


def done_handler(
    future: Future,
    name: str,
    exit_event: settings.Event | settings.PEvent,
    is_process=False,
) -> None:
    logger.info(
        "MAIN: Task is done, prompting others to quit",
        name=name,
        is_process=is_process,
        future=future,
    )

    if future.exception() is not None:
        logger.exception(future.exception())

    shutdown_handler(None, None, exit_event, is_process)


def shutdown_handler(
    _signum, _frame, exit_event: settings.Event | settings.PEvent, is_process=False
) -> None:
    logger.info("MAIN: Sending exit event to all tasks in pool")
    exit_event.set()


def multiprocess_setup() -> None:
    settings.cat_lock = settings.Lock(threading.Lock())
    settings.fact_lock = settings.Lock(threading.Lock())
    settings.latest_lock = settings.Lock(threading.Lock())

    settings.telegram_updates = settings.PQueue(multiprocessing.Queue())
    settings.discord_messages = settings.PQueue(multiprocessing.Queue())
    settings.telegram_messages = settings.PQueue(multiprocessing.Queue())


async def bot_run(pexit_event: settings.PEvent) -> None:
    exit_event = settings.Event()

    with ThreadPoolExecutor(max_workers=10) as executor:
        task_submit(
            executor,
            exit_event,
            "bot.telegram",
            lambda: asyncio.run(telegram_run(exit_event)),
        )
        task_submit(
            executor,
            exit_event,
            "bot.discord",
            lambda: asyncio.run(discord_run(exit_event)),
        )

        await pexit_event.wait()

        logger.info("MAIN: Received process exit signal, sending exit event to threads")
        exit_event.set()


def process_run(func, pexit_event: settings.PEvent) -> None:
    asyncio.run(func(pexit_event))


def task_submit(
    executor: ProcessPoolExecutor | ThreadPoolExecutor,
    exit_event: settings.PEvent | settings.Event,
    name: str,
    *task,
) -> Future:
    is_process, future = (
        isinstance(executor, ProcessPoolExecutor),
        executor.submit(*task),
    )

    future.add_done_callback(
        partial(
            done_handler,
            name=name,
            is_process=is_process,
            exit_event=exit_event,
        )
    )
    logger.info(
        "MAIN: Task is submitted", name=name, is_process=is_process, future=future
    )

    return future


def main():
    multiprocess_setup()

    manager = multiprocessing.Manager()
    pexit_event = settings.PEvent(manager.Event())

    with ProcessPoolExecutor(max_workers=3) as executor:
        for s in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
            signal.signal(s, partial(shutdown_handler, exit_event=pexit_event))

        task_submit(executor, pexit_event, "bot", process_run, bot_run, pexit_event)
        task_submit(executor, pexit_event, "web", process_run, web_run, pexit_event)


if __name__ == "__main__":
    main()
