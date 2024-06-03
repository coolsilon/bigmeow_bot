import csv
from datetime import date, timedelta
from functools import reduce
from io import BytesIO, StringIO
from random import choice
from typing import Callable

import structlog
from aiohttp import ClientSession
from cowsay import cowsay
from dotenv import load_dotenv

from bigmeow import settings
from bigmeow.settings import Change, Latest, Level

load_dotenv()
logger = structlog.get_logger()

def meow_sayify(func: Callable) -> Callable:
    async def wrapped_function(*args, **kwargs) -> str:
        return meow_say(await func(*args, **kwargs))

    return wrapped_function


def meowpetrol_update_latest(current: Latest, incoming: Level | Change) -> Latest:
    field = None

    if isinstance(incoming, settings.Level):
        if incoming.date > current.level.date:
            field = "level"
    else:
        if incoming.date > current.change.date:
            field = "change"

    return current._replace(**{field: incoming}) if field else current  # type: ignore


@meow_sayify
async def meow_fact(session: ClientSession) -> str:
    url = "https://meowfacts.herokuapp.com/"

    logger.info("MEOW: Fetching a cat fact", url="https://meowfacts.herokuapp.com/")
    async with session.get(url) as response:
        response_data = await response.json()

        async with settings.fact_lock:
            return (
                settings.fact_cache.cache(
                    f'{response_data.get("data")[0]}\n    - https://github.com/wh-iterabb-it/meowfacts'
                )
                if response.status == 200
                else settings.fact_cache.get()
            )


@meow_sayify
async def meow_petrol(session: ClientSession) -> str:
    url = "https://storage.data.gov.my/commodities/fuelprice.csv"

    async with settings.latest_lock:
        if (settings.latest_cache.level.date + timedelta(days=6)) < date.today():
            logger.info("MEOW: Fetching the fuel price list", url=url)
            async with session.get(url) as response:
                settings.latest_cache = reduce(
                    meowpetrol_update_latest,
                    [
                        Level(
                            date.fromisoformat(row["date"]),
                            float(row["ron95"]),
                            float(row["ron97"]),
                            float(row["diesel"]),
                        )
                        if row["series_type"] == "level"
                        else Change(
                            date.fromisoformat(row["date"]),
                            float(row["ron95"]),
                            float(row["ron97"]),
                            float(row["diesel"]),
                        )
                        for row in csv.DictReader(StringIO(await response.text()))
                    ],
                    settings.latest_cache,
                )

        logger.info(
            (
                f"Data sourced from {url}",
                f"From {settings.latest_cache.level.date.strftime(settings.DATE_FORMAT)} to "
                f"{(settings.latest_cache.level.date + timedelta(days=6)).strftime(settings.DATE_FORMAT)}",
            )
            + tuple(
                "Price of {} is RM {} per litre ({} from last week)".format(
                    {"ron95": "RON 95", "ron97": "RON 97", "diesel": "diesel"}.get(
                        field
                    ),
                    getattr(settings.latest_cache.level, field),
                    "{:+0.2f}".format(getattr(settings.latest_cache.change, field)),
                )
                for field in ("ron95", "ron97", "diesel")
            )
        )
        return "\n\n".join(
            (
                f"Data sourced from {url}",
                f"From {settings.latest_cache.level.date.strftime(settings.DATE_FORMAT)} to "
                f"{(settings.latest_cache.level.date + timedelta(days=6)).strftime(settings.DATE_FORMAT)}",
            )
            + tuple(
                "Price of {} is RM {} per litre ({} from last week)".format(
                    {"ron95": "RON 95", "ron97": "RON 97", "diesel": "diesel"}.get(
                        field
                    ),
                    getattr(settings.latest_cache.level, field),
                    "{:+0.2f}".format(getattr(settings.latest_cache.change, field)),
                )
                for field in ("ron95", "ron97", "diesel")
            )
        )


async def meow_fetch_photo(session: ClientSession) -> BytesIO:
    url = "https://cataas.com/cat/says/meow?type=square"

    logger.info("MEOW: Fetching a cat photo", url=url)
    async with session.get(url) as response:
        async with settings.cat_lock:
            return (
                settings.cat_cache.cache(BytesIO(await response.read()))
                if response.status == 200
                else settings.cat_cache.get()
            )


def meow_say(message: str) -> str:
    return "```\n{}\n```".format(
        cowsay(message, cow=choice(["kitty", "hellokitty", "meow"]))
    )