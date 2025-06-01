import asyncio
import contextlib
import threading
from abc import ABC
from ast import literal_eval
from datetime import date
from enum import Enum
from io import BytesIO
from os import environ
from queue import Queue
from random import choice, randint, shuffle
from typing import NamedTuple

import pytz
import structlog
from attr import dataclass
from dotenv import load_dotenv

logger = structlog.get_logger().bind(module=__name__)

load_dotenv()


# TODO use proper typing and abstrct to abstract class in py3.12
class CatCache:
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


class FactCache:
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


@dataclass
class Lock(contextlib.AbstractAsyncContextManager):
    lock: threading.Lock

    async def __aenter__(self) -> None:
        await asyncio.to_thread(self.lock.acquire)

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        self.lock.release()


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
    cat_lock: Lock

    facts: FactCache
    fact_lock: Lock

    petrol: PetrolPrice
    petrol_lock: Lock

    tasks: Queue

try:
    DEBUG = literal_eval(environ.get("DEBUG", "False"))
except Exception:
    DEBUG = False

QUEUE_TIMEOUT = int(environ.get("QUEUE_TIMEOUT", 5))

WEBHOOK_URL = environ.get("WEBHOOK_URL", "http://localhost:8000/webhook")
WEBHOOK_PORT = int(environ.get("WEBHOOK_PORT") or "8080")

WEB_SECRET_PING = environ["WEB_SECRET_PING"]
WEB_SECRET_PASSWORD = environ["WEB_SECRET_PASSWORD"]
WEB_SECRET_PING_USER = "BigMeow"

CACHE_LIMIT = 5
DATE_FORMAT = "%d/%m/%Y"

TELEGRAM_WEBHOOK = "/webhook/telegram"
TELEGRAM_USER = environ["TELEGRAM_USER"]
TELEGRAM_TOKEN = environ["TELEGRAM_TOKEN"]
TELEGRAM_WEB_TOKEN = environ["WEB_TELEGRAM_TOKEN"]

DISCORD_TOKEN = environ["DISCORD_TOKEN"]
DISCORD_USER = int(environ["DISCORD_USER"])

ECHO_WEBHOOK = "/webhook/echo"

TASK_DEFAULT_STORE = "default"
TASK_DEFAULT_EXECUTOR = "default"

TIMEZONE = pytz.utc

DATABASE_URL = environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://dbadmin:abc123@localhost:5432/bigmeow",
)

IFTTT_KEY = environ.get("IFTTT_KEY")