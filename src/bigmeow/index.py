import csv
import os
from datetime import date, timedelta
from functools import reduce
from io import BytesIO, StringIO
from random import choice, randint, shuffle
from typing import NamedTuple, NoReturn

import discord
import requests
import structlog
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


class Cat_Cache:
    cat_list: list[BytesIO] = []

    def cache(self, cat: BytesIO) -> BytesIO:
        logger.info("Storing a cat into the cache")

        if len(self.cat_list) > CAT_CACHE_LIMIT:
            self.cat_list[randint(0, CAT_CACHE_LIMIT - 1)] = cat
        else:
            self.cat_list.append(cat)

        shuffle(self.cat_list)

        return cat

    def get(self) -> BytesIO:
        logger.info("Fetching a cat from cache")
        return choice(self.cat_list)


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


CAT_CACHE_LIMIT = 5
DATE_FORMAT = "%d/%m/%Y"

logger = structlog.get_logger()
client = discord.Client()
cat_cache = Cat_Cache()


def meowpetrol_update_latest(current: Latest, incoming: Level | Change) -> Latest:
    field = None

    if isinstance(incoming, Level):
        if incoming.date > current.level.date:
            field = "level"
    else:
        if incoming.date > current.change.date:
            field = "change"

    return current._replace(**{field: incoming}) if field else current  # type: ignore


def meowpetrol_fetch_price() -> list[str]:
    result = []
    result.append(
        "Request received, fetching and parsing data from https://storage.data.gov.my/commodities/fuelprice.csv"
    )

    response = requests.get("https://storage.data.gov.my/commodities/fuelprice.csv")
    latest = reduce(
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
            for row in csv.DictReader(StringIO(response.text))
        ],
        Latest(Level(date.min, 0, 0, 0), Change(date.min, 0, 0, 0)),
    )

    result.append(
        f"From {latest.level.date.strftime(DATE_FORMAT)} to "
        f"{(latest.level.date + timedelta(days=6)).strftime(DATE_FORMAT)}"
    )
    for field in ("ron95", "ron97", "diesel"):
        result.append(
            "Price of {} is RM {} per litre ({} from last week)".format(
                {"ron95": "RON 95", "ron97": "RON 97", "diesel": "diesel"}.get(field),
                getattr(latest.level, field),
                "{:+0.2f}".format(getattr(latest.change, field)),
            )
        )

    return result


def meow_fetch_photo() -> BytesIO:
    logger.info("Fetching cat photo from cataas.com")
    response = requests.get("https://cataas.com/cat/says/meow?type=square", stream=True)

    return (
        cat_cache.cache(BytesIO(response.raw.read()))
        if response.status_code == 200
        else cat_cache.get()
    )


@client.event
async def on_message(message) -> None:
    if message.author == client.user:
        return

    if message.content.startswith("!meowpetrol"):
        logger.info(message)
        messages = meowpetrol_fetch_price()

        for text in messages:
            await message.channel.send(text)

    if "meow" in message.content.lower():
        logger.info(message)
        await message.channel.send(
            file=discord.File(meow_fetch_photo(), filename="meow.png")
        )


@client.event
async def on_ready() -> NoReturn:
    """
    Get telegram setup done here
    """
    application = ApplicationBuilder().token(os.environ["TELEGRAM_TOKEN"]).build()

    application.add_handler(CommandHandler("meowpetrol", telegram_petrol))
    application.add_handler(MessageHandler(filters.TEXT, telegram_meow))

    await application.initialize()
    await application.start()

    queue = await application.updater.start_polling()

    while True:
        update = await queue.get()
        logger.info("TG", update=update)
        queue.task_done()


async def telegram_petrol(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(update)
    messages = meowpetrol_fetch_price()

    for text in messages:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text)


async def telegram_meow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if "meow" in update.message.text:
        logger.info(update)
        await context.bot.send_photo(
            chat_id=update.effective_chat.id, photo=meow_fetch_photo()
        )


if __name__ == "__main__":
    load_dotenv()
    client.run(os.environ["DISCORD_TOKEN"])
