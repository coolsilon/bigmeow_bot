import asyncio
import logging
import threading
from abc import ABC
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import date
from enum import Enum
from io import BytesIO
from queue import Queue
from random import choice, randint, shuffle
from typing import Any, Awaitable, NamedTuple

import structlog
from attr import dataclass

from bigmeow import settings


def get_logger(module_name: str) -> structlog.stdlib.BoundLogger:
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
    )
    return structlog.get_logger().bind(module=module_name)


logger = get_logger(__name__)


# TODO use proper typing and abstrct to abstract class in py3.12
class CatCache:
    cat_list: list[BytesIO] = []

    def cache(self, cat: BytesIO) -> BytesIO:
        logger.info("CAT_CACHE: Storing a new photo to cache")

        if len(self.cat_list) > settings.CACHE_LIMIT:
            self.cat_list[randint(0, settings.CACHE_LIMIT - 1)] = cat
        else:
            self.cat_list.append(cat)

        shuffle(self.cat_list)

        return cat

    def get(self) -> BytesIO:
        assert len(self.cat_list) > 0

        logger.info("CAT_CACHE: Retrieve a photo")
        return choice(self.cat_list)


class FactCache:
    fact_list: list[str] = []

    def cache(self, fact: str) -> str:
        logger.info("FACT_CACHE: Storing a new fact to cache")

        if len(self.fact_list) > settings.CACHE_LIMIT:
            self.fact_list[randint(0, settings.CACHE_LIMIT - 1)] = fact
        else:
            self.fact_list.append(fact)

        shuffle(self.fact_list)

        return fact

    def get(self) -> str:
        assert len(self.fact_list) > 0

        logger.info("FACT_CACHE: Retrieve a fact")
        return choice(self.fact_list)


@dataclass
class PetrolRow(ABC):
    date: date
    ron95: float
    ron97: float
    diesel: float


class PetrolLevel(PetrolRow):
    pass


class PetrolChange(PetrolRow):
    pass


class PetrolPrice(NamedTuple):
    level: PetrolLevel
    change: PetrolChange


class MeowCommand(Enum):
    SAY = "meowsay"
    PETROL = "meowpetrol"
    FACT = "meowfact"
    ISBLOCKED = "meowisblocked"
    THINK = "meowthink"
    PROMPT = "meowprompt"
    HELP = "meowhelp"
    REMIND = "meowremind"

    def telegram(self) -> str:
        COMMAND_PREFIX = "/"

        return f"{COMMAND_PREFIX}{self.value}"

    def __str__(self) -> str:
        COMMAND_PREFIX = "!"

        return f"{COMMAND_PREFIX}{self.value}"


@dataclass
class TelegramSyncStore:
    messages: Queue
    updates: Queue


@dataclass
class DiscordSyncStore:
    messages: Queue


@dataclass
class SyncStore:
    exit_event: threading.Event
    telegram: TelegramSyncStore
    discord: DiscordSyncStore

    cats: CatCache
    cat_lock: threading.Lock

    facts: FactCache
    fact_lock: threading.Lock

    petrol: PetrolPrice
    petrol_lock: threading.Lock

    tasks: Queue


@asynccontextmanager
async def async_lock(lock: threading.Lock):
    await asyncio.to_thread(lock.acquire)

    try:
        yield
    finally:
        lock.release()


def message_contains(message: str | None, content: str, is_command=True) -> bool:
    message = message or ""

    return (message.startswith(content)) if is_command else (content in message.lower())

async def coroutine_repeat_queue(
    coro_func: Callable[..., Awaitable[None]], *args: Any
) -> None:
    try:
        while True:
            await coro_func(*args)
    except asyncio.CancelledError:
        pass