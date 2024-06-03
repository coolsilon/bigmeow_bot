import secrets
from asyncio import Lock
from datetime import date
from enum import Enum
from io import BytesIO
from random import choice, randint, shuffle
from typing import NamedTuple

import structlog

logger = structlog.getLogger()


# TODO use proper typing and abstrct to abstract class in py3.12
class Cat_Cache:
    cat_list: list[BytesIO] = []

    def cache(self, cat: BytesIO) -> BytesIO:
        logger.info("Storing a cat into the cache")

        if len(self.cat_list) > CACHE_LIMIT:
            self.cat_list[randint(0, CACHE_LIMIT - 1)] = cat
        else:
            self.cat_list.append(cat)

        shuffle(self.cat_list)

        return cat

    def get(self) -> BytesIO:
        assert len(self.cat_list) > 0

        logger.info("Fetching a cat from cache")
        return choice(self.cat_list)


class Fact_Cache:
    fact_list: list[str] = []

    def cache(self, fact: str) -> str:
        logger.info("Storing a fact into the cache")

        if len(self.fact_list) > CACHE_LIMIT:
            self.fact_list[randint(0, CACHE_LIMIT - 1)] = fact
        else:
            self.fact_list.append(fact)

        shuffle(self.fact_list)

        return fact

    def get(self) -> str:
        assert len(self.fact_list) > 0

        logger.info("Fetching a fact from cache")
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

    def telegram(self) -> str:
        COMMAND_PREFIX = "/"

        return f"{COMMAND_PREFIX}{self.value}"

    def __str__(self) -> str:
        COMMAND_PREFIX = "!"

        return f"{COMMAND_PREFIX}{self.value}"


cat_cache, cat_lock = Cat_Cache(), Lock()
fact_cache, fact_lock = Fact_Cache(), Lock()
latest_cache, latest_lock = (
    Latest(Level(date.min, 0, 0, 0), Change(date.min, 0, 0, 0)),
    Lock(),
)

CACHE_LIMIT = 5
DATE_FORMAT = "%d/%m/%Y"
SECRET_TOKEN = secrets.token_hex(128)