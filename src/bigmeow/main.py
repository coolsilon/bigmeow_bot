import asyncio
import signal
import threading
from collections.abc import Callable
from concurrent.futures import Future, ProcessPoolExecutor
from dataclasses import dataclass
from types import FrameType
from typing import Annotated, Any

import typer
from structlog.stdlib import BoundLogger

from bigmeow import discord, scheduler, settings, telegram, web
from bigmeow.common import get_logger


@dataclass
class ShutdownHandler:
    exit_event: threading.Event
    logger: BoundLogger

    def __call__(self, signum: int | None, frame: FrameType | None) -> None:
        self.logger.info("MAIN: Sending exit event to all tasks in pool")
        self.exit_event.set()


@dataclass
class DoneHandler:
    name: str
    exit_event: threading.Event
    logger: BoundLogger
    shutdown_handler: ShutdownHandler

    def __call__(self, future: Future) -> None:
        self.logger.info(
            "MAIN: Task is done, prompting others to quit",
            name=self.name,
            future=future,
        )

        if future.exception() is not None:
            self.logger.exception(future.exception())  # type: ignore

        self.shutdown_handler(None, None)


def process_run(func, exit_event: threading.Event, *arguments) -> None:
    asyncio.run(func(exit_event, *arguments))


def task_submit(
    run: bool,
    executor: ProcessPoolExecutor,
    exit_event: threading.Event,
    name: str,
    func: Callable[..., Any],
    shutdown_handler: ShutdownHandler,
    logger: BoundLogger,
    *arguments: Any,
) -> Future | None:
    if run:
        future = executor.submit(process_run, func, exit_event, *arguments)

        future.add_done_callback(
            DoneHandler(name, exit_event, logger, shutdown_handler)
        )
        logger.info("MAIN: Task is submitted", name=name, future=future)

        return future


def main(
    run_discord: Annotated[bool, typer.Option(" /--nodiscord")] = True,
    run_telegram: Annotated[bool, typer.Option(" /--notg")] = True,
) -> None:
    logger = get_logger(__name__)
    exit_event = settings.manager.Event()

    with ProcessPoolExecutor(max_workers=10) as executor:
        shutdown_handler = ShutdownHandler(exit_event, logger)

        for s in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
            signal.signal(s, shutdown_handler)

        foo = []
        bar = task_submit(
            run_telegram,
            executor,
            exit_event,
            "bot.telegram",
            telegram.run,
            shutdown_handler,
            logger,
        )
        foo.append(bar)

        bar = task_submit(
            run_discord,
            executor,
            exit_event,
            "bot.discord",
            discord.run,
            shutdown_handler,
            logger,
        )
        foo.append(bar)

        bar = task_submit(
            True,
            executor,
            exit_event,
            "scheduler",
            scheduler.run,
            shutdown_handler,
            logger,
        )
        foo.append(("s", bar))

        bar = task_submit(
            True,
            executor,
            exit_event,
            "web",
            web.run,
            shutdown_handler,
            logger,
        )
        foo.append(bar)


if __name__ == "__main__":
    typer.run(main)
