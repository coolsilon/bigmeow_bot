import asyncio
import multiprocessing
import signal
import threading
from concurrent.futures import Future, ProcessPoolExecutor, ThreadPoolExecutor
from functools import partial
from os import makedirs
from typing import Annotated, Any, Callable

import structlog
import typer
import uvloop
from dotenv import load_dotenv

import bigmeow.settings as settings
from bigmeow.discord import run as discord_run
from bigmeow.slack import run as slack_run
from bigmeow.telegram import run as telegram_run
from bigmeow.web import run as web_run

load_dotenv()

logger = structlog.get_logger()

def done_handler(
    future: Future,
    name: str,
    exit_event: threading.Event,
    logger: Any,
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

    shutdown_handler(None, None, exit_event, logger, is_process)


def shutdown_handler(
    _signum, _frame, exit_event: threading.Event, logger: Any, is_process=False
) -> None:
    logger.info("MAIN: Sending exit event to all tasks in pool")
    exit_event.set()


async def bot_run(
    pexit_event: threading.Event,
    run_telegram: bool,
    run_slack: bool,
    run_discord: bool,
    logger: Any,
) -> None:
    exit_event = threading.Event()

    with ThreadPoolExecutor(max_workers=10) as executor:
        task_submit(
            run_telegram,
            executor,
            exit_event,
            "bot.telegram",
            telegram_run,
            logger=logger,
        )
        task_submit(
            run_discord, executor, exit_event, "bot.discord", discord_run, logger=logger
        )
        task_submit(
            run_slack, executor, exit_event, "bot.slack", slack_run, logger=logger
        )

        await asyncio.to_thread(pexit_event.wait)

        logger.info("MAIN: Received process exit signal, sending exit event to threads")
        exit_event.set()


def process_run(func, pexit_event: threading.Event, *arguments) -> None:
    uvloop.run(func(pexit_event, *arguments))

def task_submit(
    run: bool,
    executor: ProcessPoolExecutor | ThreadPoolExecutor,
    exit_event: threading.Event,
    name: str,
    func: Callable[..., Any],
    *arguments: Any,
    logger: Any,
) -> Future | None:
    if run:
        is_process, future = (
            isinstance(executor, ProcessPoolExecutor),
            executor.submit(process_run, func, exit_event, *arguments),
        )

        future.add_done_callback(
            partial(
                done_handler,
                name=name,
                is_process=is_process,
                exit_event=exit_event,
                logger=logger,
            )
        )
        logger.info(
            "MAIN: Task is submitted", name=name, is_process=is_process, future=future
        )

        return future


def main(
    run_web: Annotated[bool, typer.Option(" /--noweb")] = True,
    run_discord: Annotated[bool, typer.Option(" /--nodiscord")] = True,
    run_telegram: Annotated[bool, typer.Option(" /--notg")] = True,
    run_slack: Annotated[bool, typer.Option(" /--noslack")] = True,
) -> None:
    manager = multiprocessing.Manager()
    pexit_event = manager.Event()

    if run_slack:
        makedirs(settings.data_path_slack, exist_ok=True)

    with ProcessPoolExecutor(max_workers=3) as executor:
        for s in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
            signal.signal(
                s, partial(shutdown_handler, exit_event=pexit_event, logger=logger)
            )

        task_submit(
            True,
            executor,
            pexit_event,
            "bot",
            bot_run,
            run_telegram,
            run_slack,
            run_discord,
            logger,
            logger=logger,
        )

        task_submit(run_web, executor, pexit_event, "web", web_run, logger=logger)


if __name__ == "__main__":
    typer.run(main)
