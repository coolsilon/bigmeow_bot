import asyncio
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from multiprocessing.managers import ListProxy
from queue import Empty, Queue
from typing import Any

from apscheduler import events
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from structlog.stdlib import BoundLogger

from bigmeow import common, settings
from bigmeow.common import coroutine_repeat_queue, get_logger


@dataclass
class ScheduledUpdater:
    scheduler: AsyncIOScheduler
    event_loop: asyncio.AbstractEventLoop
    scheduled: ListProxy
    lock: asyncio.Lock
    logger: BoundLogger

    def __call__(self, event):
        self.event_loop.create_task(self.run(event))

    async def run(self, event):
        self.logger.info("Updating jobs", on_event=event)
        async with self.lock:
            self.scheduled[:] = self.scheduler.get_jobs()


async def task_consume(
    scheduler: AsyncIOScheduler, queue: Queue, logger: BoundLogger
) -> None:
    with suppress(Empty):
        task = await asyncio.to_thread(queue.get, timeout=settings.QUEUE_TIMEOUT)

        logger.info("Retrieved task", **task)
        scheduler.add_job(**task)


async def run(
    sync_store: common.SyncStore, logger: BoundLogger = get_logger(__name__)
) -> None:
    logger.info("SCHEDULER: Starting")
    scheduler = AsyncIOScheduler(
        timezone=settings.TIMEZONE,
        logger=logger,
        jobstores={
            settings.TASK_DEFAULT_STORE: SQLAlchemyJobStore(settings.DATABASE_URL)
        },
        executors={
            settings.TASK_DEFAULT_EXECUTOR: AsyncIOExecutor(),
        },
    )
    scheduler.add_listener(
        ScheduledUpdater(
            scheduler,
            asyncio.get_running_loop(),
            sync_store.scheduled,
            asyncio.Lock(),
            logger,
        ),
        events.EVENT_ALL,
    )
    scheduler.start()

    logger.info("SCHEDULER: Ready for requests")
    asyncio.create_task(
        coroutine_repeat_queue(task_consume, scheduler, sync_store.tasks, logger)
    )

    await asyncio.to_thread(sync_store.exit_event.wait)

    logger.info("SCHEDULER: Stopping")

    scheduler.shutdown()
