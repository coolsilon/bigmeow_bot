import asyncio
import contextlib
import queue
import secrets
import threading
from datetime import date
from enum import Enum
from functools import partial
from io import BytesIO
from random import choice, randint, shuffle
from typing import Any, NamedTuple

import structlog

logger = structlog.get_logger()


# TODO use proper typing and abstrct to abstract class in py3.12
class Cat_Cache:
    cat_list: list[BytesIO] = []

    def cache(self, cat: BytesIO) -> BytesIO:
        logger.info("CAT_CACHE: Storing a new photo to cache")

        if len(self.cat_list) > CACHE_LIMIT:
            self.cat_list[randint(0, CACHE_LIMIT - 1)] = cat
        else:
            self.cat_list.append(cat)

        shuffle(self.cat_list)

        return cat

    def get(self) -> BytesIO:
        assert len(self.cat_list) > 0

        logger.info("CAT_CACHE: Retrieve a photo")
        return choice(self.cat_list)


class Event(threading.Event):
    async def wait(self, timeout: int | None = 5) -> bool:
        while True:
            task = asyncio.get_event_loop().run_in_executor(
                None, partial(super().wait, timeout)
            )
            await task

            if result := task.result():
                return result


class Queue(queue.Queue):
    async def put(
        self, item: dict[Any, Any], block: bool = True, timeout: int | None = None
    ) -> None:
        task = asyncio.get_event_loop().run_in_executor(
            None, partial(super().put, item, block, timeout)
        )
        await task

        return task.result()

    async def get(self, block: bool = True, timeout: int | None = 5) -> dict[Any, Any]:
        while True:
            task = asyncio.get_event_loop().run_in_executor(
                None, partial(super().get, block, timeout)
            )

            with contextlib.suppress(queue.Empty):
                await task

            if task.done() and task.exception() is None:
                return task.result()


class Lock(contextlib.AbstractAsyncContextManager):
    def __init__(self, lock: threading.Lock) -> None:
        self.lock = lock

    async def __aenter__(self) -> None:
        await self.acquire()

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return self.release()

    async def acquire(self) -> bool:
        task = asyncio.get_event_loop().run_in_executor(None, self.lock.acquire)
        await task

        return task.result()

    def release(self) -> None:
        self.lock.release()

    def locked(self) -> bool:
        return self.lock.locked()


class Fact_Cache:
    fact_list: list[str] = []

    def cache(self, fact: str) -> str:
        logger.info("FACT_CACHE: Storing a new fact to cache")

        if len(self.fact_list) > CACHE_LIMIT:
            self.fact_list[randint(0, CACHE_LIMIT - 1)] = fact
        else:
            self.fact_list.append(fact)

        shuffle(self.fact_list)

        return fact

    def get(self) -> str:
        assert len(self.fact_list) > 0

        logger.info("FACT_CACHE: Retrieve a fact")
        return choice(self.fact_list)


class Row(NamedTuple):
    date: date
    ron95: float
    ron97: float
    diesel: float


class Level(Row):
    pass


class Change(Row):
    pass


class Latest(NamedTuple):
    level: Level
    change: Change


class MeowCommand(Enum):
    SAY = "meowsay"
    PETROL = "meowpetrol"
    FACT = "meowfact"
    ISBLOCKED = "meowisblocked"
    THINK = "meowthink"

    def telegram(self) -> str:
        COMMAND_PREFIX = "/"

        return f"{COMMAND_PREFIX}{self.value}"

    def __str__(self) -> str:
        COMMAND_PREFIX = "!"

        return f"{COMMAND_PREFIX}{self.value}"


cat_cache, cat_lock = Cat_Cache(), asyncio.Lock()
fact_cache, fact_lock = Fact_Cache(), asyncio.Lock()
latest_cache, latest_lock = (
    Latest(Level(date.min, 0, 0, 0), Change(date.min, 0, 0, 0)),
    asyncio.Lock(),
)

CACHE_LIMIT = 5
DATE_FORMAT = "%d/%m/%Y"
SECRET_TOKEN = secrets.token_hex(128)

telegram_queue = asyncio.Queue()
