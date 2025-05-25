import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from queue import Empty
from threading import Event

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from structlog.stdlib import BoundLogger

from bigmeow import settings
from bigmeow.common import coroutine_repeat_queue, get_logger


async def task_consume(scheduler, logger) -> None:
    try:
        with suppress(Empty):
            task = await asyncio.to_thread(
                settings.task_queue.get, timeout=settings.QUEUE_TIMEOUT
            )

            logger.info("Retrieved task", **task)
            scheduler.add_job(**task)
    except asyncio.CancelledError:
        pass


async def run(exit_event: Event, logger: BoundLogger = get_logger(__name__)) -> None:
    scheduler = AsyncIOScheduler(
        timezone=settings.TIMEZONE,
        logger=logger,
        jobstores={
            settings.TASK_DEFAULT_STORE: SQLAlchemyJobStore(settings.DATABASE_URL)
        },
        # FIXME might need to also consider process pool in future
        executors={settings.TASK_DEFAULT_EXECUTOR: ThreadPoolExecutor(10)},
    )
    scheduler.start()

    asyncio.create_task(coroutine_repeat_queue(task_consume, scheduler, logger))

    await asyncio.to_thread(exit_event.wait)
