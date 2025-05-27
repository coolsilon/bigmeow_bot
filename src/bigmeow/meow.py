import asyncio
import csv
from datetime import date, datetime, timedelta
from functools import reduce
from io import BytesIO, StringIO
from queue import Queue
from random import choice
from typing import Any, Callable

import dateparser
import httpx
from apscheduler.triggers.date import DateTrigger
from cowsay import cowsay, cowthink
from structlog.stdlib import BoundLogger

from bigmeow import settings
from bigmeow.common import get_logger
from bigmeow.settings import Latest, PetrolChange, PetrolLevel


def meow_sayify(func: Callable) -> Callable:
    async def wrapped_function(*args, **kwargs) -> str:
        return meow_say(await func(*args, **kwargs), wrap_text=False)

    return wrapped_function


@meow_sayify
async def meow_blockedornot(
    client: httpx.AsyncClient, query: str, logger: BoundLogger = get_logger(__name__)
) -> str:
    url = "https://blockedornot.sinarproject.org/api/"

    logger.info("MEOW: Fetching blocked query", url=url, query=query)
    response = await client.get(url, params={"query": query})
    result = [f"Website {query} is safe."]

    response_data = response.json()

    if response_data["blocked"] and response_data["different_ip"]:
        result = [f"Website {query} is blocked."]

    elif not response_data["blocked"] and response_data["different_ip"]:
        result = [f"Website {query} is likely safe."]

    if response_data["measurement"]:
        result = result + [f"Measurement URL: {response_data['measurement']}"]

    return "\n".join(result + ["Powered by https://blockedornot.sinarproject.org/"])


def meowpetrol_update_latest(
    current: Latest, incoming: PetrolLevel | PetrolChange
) -> Latest:
    field = None

    if isinstance(incoming, PetrolLevel):
        if incoming.date > current.level.date:
            field = "level"
    else:
        if incoming.date > current.change.date:
            field = "change"

    return current._replace(**{field: incoming}) if field else current  # type: ignore


@meow_sayify
async def meow_fact(
    client: httpx.AsyncClient, logger: BoundLogger = get_logger(__name__)
) -> str:
    url = "https://meowfacts.herokuapp.com/"

    logger.info("MEOW: Fetching a cat fact", url=url)
    response = await client.get(url)
    response_data = response.json()

    async with settings.fact_lock:
        return (
            settings.fact_cache.cache(
                f"{response_data.get('data')[0]}\n    - https://github.com/wh-iterabb-it/meowfacts"
            )
            if response.status_code == 200
            else settings.fact_cache.get()
        )


@meow_sayify
async def meow_petrol(
    client: httpx.AsyncClient, logger: BoundLogger = get_logger(__name__)
) -> str:
    url = "https://storage.data.gov.my/commodities/fuelprice.csv"

    async with settings.latest_lock:
        if (settings.latest_cache.level.date + timedelta(days=6)) < date.today():
            logger.info("MEOW: Fetching the fuel price list", url=url)
            response = await client.get(url)
            settings.latest_cache = reduce(
                meowpetrol_update_latest,
                [
                    PetrolLevel(
                        date.fromisoformat(row["date"]),
                        float(row["ron95"]),
                        float(row["ron97"]),
                        float(row["diesel"]),
                    )
                    if row["series_type"] == "level"
                    else PetrolChange(
                        date.fromisoformat(row["date"]),
                        float(row["ron95"]),
                        float(row["ron97"]),
                        float(row["diesel"]),
                    )
                    for row in csv.DictReader(StringIO(response.text))
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


async def meow_fetch_photo(
    client: httpx.AsyncClient, logger: BoundLogger = get_logger(__name__)
) -> BytesIO:
    url = "https://cataas.com/cat/says/meow?type=square"

    logger.info("MEOW: Fetching a cat photo", url=url)
    response = await client.get(url)

    async with settings.cat_lock:
        return (
            settings.cat_cache.cache(BytesIO(response.read()))
            if response.status_code == 200
            else settings.cat_cache.get()
        )


async def meow_prompt(
    client: httpx.AsyncClient,
    message: str,
    channel: str,
    destination: str,
    logger: BoundLogger = get_logger(__name__),
) -> None:
    url = f"https://maker.ifttt.com/trigger/prompt/with/key/{settings.IFTTT_KEY}"
    data = {"value1": message, "value2": channel, "value3": destination}

    logger.info("MEOW: Sending IFTTT request", ifttt_event="prompt", data=data)
    response = await client.post(url, json=data)
    logger.info("MEOW: IFTTT response", response=response.text)


async def meow_remind(
    message: str, queue: Queue, data_builder: Callable[[str], dict[str, Any]]
) -> str:
    text, when = message.rsplit("@", maxsplit=1)
    when = dateparser.parse(when, settings={"TIMEZONE": settings.TIMEZONE.zone})  # type: ignore

    assert when

    await asyncio.to_thread(
        settings.task_queue.put,
        {
            "func": "bigmeow.scheduler:execute_sync",
            "trigger": DateTrigger(when, settings.TIMEZONE),
            "args": (
                queue.put,
                data_builder(meow_say(text)),
            ),
            "misfire_grace_time": None,
        },
    )

    return f"Scheduled message: {text}\nTime: {when}"


def meow_say(message: str, is_cowthink: bool = False, wrap_text: bool = True) -> str:
    func = cowthink if is_cowthink else cowsay

    return "```\n{}\n```".format(
        func(message, wrap_text=wrap_text, cow=choice(["kitty", "hellokitty", "meow"]))
    )