import asyncio
import multiprocessing
import signal
from collections.abc import Callable
from concurrent.futures import Future, ProcessPoolExecutor
from dataclasses import dataclass
from datetime import date
from types import FrameType
from typing import Annotated, Any

import typer
from structlog.stdlib import BoundLogger

from bigmeow import discord, scheduler, settings, telegram, web
from bigmeow.common import get_logger


@dataclass
class ShutdownHandler:
    sync_store: settings.SyncStore
    logger: BoundLogger

    def __call__(self, signum: int | None, frame: FrameType | None) -> None:
        self.logger.info("MAIN: Sending exit event to all tasks in pool")
        self.sync_store.exit_event.set()


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


def process_run(func, sync_store: settings.SyncStore, *arguments) -> None:
    asyncio.run(func(sync_store, *arguments))


def task_submit(
    run: bool,
    executor: ProcessPoolExecutor,
    sync_store: settings.SyncStore,
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
    sync_store = settings.SyncStore(
        manager.Event(),
        settings.TelegramSyncStore(manager.Queue(), manager.Queue()),
        settings.DiscordSyncStore(manager.Queue()),
        settings.CatCache(),
        settings.Lock(manager.Lock()),
        settings.FactCache(),
        settings.Lock(manager.Lock()),
        settings.PetrolPrice(
            settings.PetrolLevel(date.min, 0, 0, 0),
            settings.PetrolChange(date.min, 0, 0, 0),
        ),
        settings.Lock(manager.Lock()),
        manager.Queue(),
    )

    with ProcessPoolExecutor(max_workers=10) as executor:
        shutdown_handler = ShutdownHandler(sync_store, logger)

        for s in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
            signal.signal(s, shutdown_handler)

        foo = []
        bar = task_submit(
            run_telegram,
            executor,
            sync_store,
            "bot.telegram",
            telegram.run,
            shutdown_handler,
            logger,
        )
        foo.append(bar)

        bar = task_submit(
            run_discord,
            executor,
            sync_store,
            "bot.discord",
            discord.run,
            shutdown_handler,
            logger,
        )
        foo.append(bar)

        bar = task_submit(
            True,
            executor,
            sync_store,
            "scheduler",
            scheduler.run,
            shutdown_handler,
            logger,
        )
        foo.append(("s", bar))

        bar = task_submit(
            True,
            executor,
            sync_store,
            "web",
            web.run,
            shutdown_handler,
            logger,
        )
        foo.append(bar)


if __name__ == "__main__":
    typer.run(main)
