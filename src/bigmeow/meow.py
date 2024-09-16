import csv
from datetime import date, timedelta
from functools import reduce
from io import BytesIO, StringIO
from os import environ
from random import choice
from typing import Callable

import structlog
from aiohttp import ClientSession
from cowsay import cowsay, cowthink
from dotenv import load_dotenv

from bigmeow import settings
from bigmeow.settings import Change, Latest, Level

load_dotenv()
logger = structlog.get_logger()


def meow_sayify(func: Callable) -> Callable:
    async def wrapped_function(*args, **kwargs) -> str:
        return meow_say(await func(*args, **kwargs), wrap_text=False)

    return wrapped_function


@meow_sayify
async def meow_blockedornot(session: ClientSession, query: str) -> str:
    url = "https://blockedornot.sinarproject.org/api/"

    logger.info("MEOW: Fetching blocked query", url=url, query=query)
    async with session.get(url, params={"query": query}) as response:
        result = [f"Website {query} is safe."]

        response_data = await response.json()

        if response_data["blocked"] and response_data["different_ip"]:
            result = [f"Website {query} is blocked."]

        elif not response_data["blocked"] and response_data["different_ip"]:
            result = [f"Website {query} is likely safe."]

        if response_data["measurement"]:
            result = result + [f"Measurement URL: {response_data['measurement']}"]

        return "\n".join(result + ["Powered by https://blockedornot.sinarproject.org/"])


def meowpetrol_update_latest(current: Latest, incoming: Level | Change) -> Latest:
    field = None

    if isinstance(incoming, Level):
        if incoming.date > current.level.date:
            field = "level"
    else:
        if incoming.date > current.change.date:
            field = "change"

    return current._replace(**{field: incoming}) if field else current  # type: ignore


@meow_sayify
async def meow_fact(session: ClientSession) -> str:
    url = "https://meowfacts.herokuapp.com/"

    logger.info("MEOW: Fetching a cat fact", url=url)
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


async def meow_prompt(
    session: ClientSession, message: str, channel: str, destination: str
) -> None:
    url = f"https://maker.ifttt.com/trigger/prompt/with/key/{environ.get('IFTTT_KEY')}"
    data = {"value1": message, "value2": channel, "value3": destination}

    logger.info("MEOW: Sending IFTTT request", ifttt_event="prompt", data=data)
    async with session.post(url, json=data) as response:
        logger.info("MEOW: IFTTT response", response=await response.text())


def meow_say(message: str, is_cowthink: bool = False, wrap_text: bool = True) -> str:
    func = cowthink if is_cowthink else cowsay

    return "```\n{}\n```".format(
        func(message, wrap_text=wrap_text, cow=choice(["kitty", "hellokitty", "meow"]))
    )