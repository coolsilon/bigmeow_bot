import asyncio
import multiprocessing
import signal
import threading
from collections.abc import Callable
from concurrent.futures import Future, ProcessPoolExecutor
from dataclasses import dataclass
from datetime import date
from types import FrameType
from typing import Annotated, Any

import typer
from structlog.stdlib import BoundLogger

from bigmeow import common, discord, scheduler, telegram, web
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


def process_run(func, sync_store: common.SyncStore, *arguments) -> None:
    asyncio.run(func(sync_store, *arguments))


def task_submit(
    run: bool,
    executor: ProcessPoolExecutor,
    sync_store: common.SyncStore,
    name: str,
    func: Callable[..., Any],
    shutdown_handler: ShutdownHandler,
    logger: BoundLogger,
    *arguments: Any,
) -> Future | None:
    if run:
        future = executor.submit(process_run, func, sync_store, *arguments)

        future.add_done_callback(DoneHandler(name, logger, shutdown_handler))
        logger.info("MAIN: Task is submitted", name=name, future=future)

        return future


def main(
    run_discord: Annotated[bool, typer.Option(" /--nodiscord")] = True,
    run_telegram: Annotated[bool, typer.Option(" /--notg")] = True,
) -> None:
    logger = get_logger(__name__)

    manager = multiprocessing.Manager()
    sync_store = common.SyncStore(
        manager.Event(),
        common.TelegramSyncStore(manager.Queue(), manager.Queue()),
        common.DiscordSyncStore(manager.Queue()),
        common.CatCache(),
        manager.Lock(),
        common.FactCache(),
        manager.Lock(),
        common.PetrolPrice(
            common.PetrolLevel(date.min, 0, 0, 0),
            common.PetrolChange(date.min, 0, 0, 0),
        ),
        manager.Lock(),
        manager.Queue(),
    )

    with ProcessPoolExecutor(max_workers=10) as executor:
        shutdown_handler = ShutdownHandler(sync_store.exit_event, logger)

        for s in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
            signal.signal(s, shutdown_handler)

        task_submit(
            run_telegram,
            executor,
            sync_store,
            "bot.telegram",
            telegram.run,
            shutdown_handler,
            logger,
        )

        task_submit(
            run_discord,
            executor,
            sync_store,
            "bot.discord",
            discord.run,
            shutdown_handler,
            logger,
        )

        task_submit(
            True,
            executor,
            sync_store,
            "scheduler",
            scheduler.run,
            shutdown_handler,
            logger,
        )

        task_submit(
            True,
            executor,
            sync_store,
            "web",
            web.run,
            shutdown_handler,
            logger,
        )

    manager.shutdown()


if __name__ == "__main__":
    typer.run(main)
