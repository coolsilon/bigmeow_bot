import asyncio
import multiprocessing
import signal
from concurrent.futures import Future, ProcessPoolExecutor, ThreadPoolExecutor
from functools import partial
from typing import Annotated

import structlog
import typer
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


async def bot_run(
    pexit_event: settings.PEvent,
    run_telegram: bool = True,
    run_slack: bool = True,
    run_discord: bool = True,
) -> None:
    exit_event = settings.Event()

    with ThreadPoolExecutor(max_workers=10) as executor:
        task_submit(
            run_telegram,
            executor,
            exit_event,
            "bot.telegram",
            lambda: asyncio.run(telegram_run(exit_event)),
        )
        task_submit(
            run_discord,
            executor,
            exit_event,
            "bot.discord",
            lambda: asyncio.run(discord_run(exit_event)),
        )
        task_submit(
            run_slack,
            executor,
            exit_event,
            "bot.slack",
            lambda: asyncio.run(slack_run(exit_event)),
        )

        await pexit_event.wait()

        logger.info("MAIN: Received process exit signal, sending exit event to threads")
        exit_event.set()


def process_run(func, pexit_event: settings.PEvent) -> None:
    asyncio.run(func(pexit_event))


def task_submit(
    run: bool,
    executor: ProcessPoolExecutor | ThreadPoolExecutor,
    exit_event: settings.PEvent | settings.Event,
    name: str,
    *task,
) -> Future | None:
    if run:
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


def main(
    run_web: Annotated[bool, typer.Option(" /--noweb")] = True,
    run_discord: Annotated[bool, typer.Option(" /--nodiscord")] = True,
    run_telegram: Annotated[bool, typer.Option(" /--notg")] = True,
    run_slack: Annotated[bool, typer.Option(" /--noslack")] = True,
) -> None:
    manager = multiprocessing.Manager()
    pexit_event = settings.PEvent(manager.Event())

    with ProcessPoolExecutor(max_workers=3) as executor:
        for s in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
            signal.signal(s, partial(shutdown_handler, exit_event=pexit_event))

        task_submit(
            True,
            executor,
            pexit_event,
            "bot",
            process_run,
            partial(
                bot_run,
                run_discord=run_discord,
                run_telegram=run_telegram,
                run_slack=run_slack,
            ),
            pexit_event,
        )

        task_submit(
            run_web, executor, pexit_event, "web", process_run, web_run, pexit_event
        )


if __name__ == "__main__":
    typer.run(main)
