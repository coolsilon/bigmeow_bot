import asyncio
import contextlib
import multiprocessing
import threading
from datetime import date
from enum import Enum
from io import BytesIO
from os import environ
from pathlib import Path
from random import choice, randint, shuffle

import structlog
from attr import dataclass
from dotenv import load_dotenv

logger = structlog.get_logger().bind(module=__name__)

load_dotenv()


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


@dataclass
class Lock(contextlib.AbstractAsyncContextManager):
    lock: threading.Lock

    async def __aenter__(self) -> None:
        await asyncio.to_thread(self.lock.acquire)

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        self.lock.release()


@dataclass
class PetrolRow:
    date: date
    ron95: float
    ron97: float
    diesel: float


class PetrolLevel(PetrolRow):
    pass


class PetrolChange(PetrolRow):
    pass


@dataclass
class Latest:
    level: PetrolLevel
    change: PetrolChange


class MeowCommand(Enum):
    SAY = "meowsay"
    PETROL = "meowpetrol"
    FACT = "meowfact"
    ISBLOCKED = "meowisblocked"
    THINK = "meowthink"
    PROMPT = "meowprompt"

    def telegram(self) -> str:
        COMMAND_PREFIX = "/"

        return f"{COMMAND_PREFIX}{self.value}"

    def __str__(self) -> str:
        COMMAND_PREFIX = "!"

        return f"{COMMAND_PREFIX}{self.value}"


manager = multiprocessing.Manager()
cat_cache = Cat_Cache()
cat_lock = Lock(manager.Lock())

fact_cache = Fact_Cache()
fact_lock = Lock(manager.Lock())

latest_cache = Latest(
    PetrolLevel(date.min, 0, 0, 0),
    PetrolChange(date.min, 0, 0, 0),
)
latest_lock = Lock(manager.Lock())

QUEUE_TIMEOUT = int(environ.get("QUEUE_TIMEOUT", 5))


WEBHOOK_URL = environ.get("WEBHOOK_URL", "http://localhost:8000/webhook")
WEBHOOK_PORT = int(environ.get("WEBHOOK_PORT") or "8080")

CACHE_LIMIT = 5
DATE_FORMAT = "%d/%m/%Y"
WEB_TELEGRAM_TOKEN = environ["WEB_TELEGRAM_TOKEN"]

TELEGRAM_WEBHOOK = "/webhook/telegram"
telegram_messages = manager.Queue()
telegram_updates = manager.Queue()

DISCORD_WEBHOOK = "/webhook/discord"
discord_messages = manager.Queue()

ECHO_WEBHOOK = "/webhook/echo"

task_queue = manager.Queue()

data_path = Path(environ.get("DATA_PATH", "/data"))
data_path_slack = data_path / "slack"
