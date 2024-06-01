import csv
import os
from datetime import date, timedelta
from enum import Enum
from functools import reduce
from io import BytesIO, StringIO
from random import choice, randint, shuffle
from typing import Generator, NamedTuple, NoReturn

import discord
import requests
import structlog
from cowsay import cowsay
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


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

    def __str__(self) -> str:
        COMMAND_PREFIX = "!"

        return f"{COMMAND_PREFIX}{self.value}"


CACHE_LIMIT = 5
DATE_FORMAT = "%d/%m/%Y"

logger = structlog.get_logger()
client = discord.Client()
cat_cache = Cat_Cache()
fact_cache = Fact_Cache()
latest_cache = Latest(Level(date.min, 0, 0, 0), Change(date.min, 0, 0, 0))


def meowpetrol_update_latest(current: Latest, incoming: Level | Change) -> Latest:
    field = None

    if isinstance(incoming, Level):
        if incoming.date > current.level.date:
            field = "level"
    else:
        if incoming.date > current.change.date:
            field = "change"

    return current._replace(**{field: incoming}) if field else current  # type: ignore


def meow_fact():
    global fact_cache

    response = requests.get("https://meowfacts.herokuapp.com/")

    return (
        fact_cache.cache(response.json().get("data")[0])
        if response.status_code == 200
        else fact_cache.get()
    )


def meowpetrol_fetch_price() -> Generator[str, None, None]:
    global latest_cache

    if (latest_cache.level.date + timedelta(days=6)) < date.today():
        yield (
            "Request received, fetching and parsing data from https://storage.data.gov.my/commodities/fuelprice.csv"
        )

        response = requests.get("https://storage.data.gov.my/commodities/fuelprice.csv")
        latest_cache = reduce(
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
            latest_cache,
        )

    yield (
        f"From {latest_cache.level.date.strftime(DATE_FORMAT)} to "
        f"{(latest_cache.level.date + timedelta(days=6)).strftime(DATE_FORMAT)}"
    )

    for field in ("ron95", "ron97", "diesel"):
        yield (
            "Price of {} is RM {} per litre ({} from last week)".format(
                {"ron95": "RON 95", "ron97": "RON 97", "diesel": "diesel"}.get(field),
                getattr(latest_cache.level, field),
                "{:+0.2f}".format(getattr(latest_cache.change, field)),
            )
        )


def meow_fetch_photo() -> BytesIO:
    global cat_cache

    logger.info("Fetching cat photo from cataas.com")
    response = requests.get("https://cataas.com/cat/says/meow?type=square", stream=True)

    return (
        cat_cache.cache(BytesIO(response.raw.read()))
        if response.status_code == 200
        else cat_cache.get()
    )


def meow_say(message: str) -> str:
    return "```\n{}\n```".format(
        cowsay(message, cow=choice(["kitty", "hellokitty", "meow"]))
    )


@client.event
async def on_message(message) -> None:
    if message.author == client.user:
        return

    if message.content.startswith(str(MeowCommand.PETROL)):
        logger.info(message)
        messages = meowpetrol_fetch_price()

        for text in messages:
            await message.channel.send(text)

    elif message.content.startswith(str(MeowCommand.SAY)):
        logger.info(message)
        await message.channel.send(
            meow_say(message.content.replace("!meowsay", "").strip())
        )

    elif message.content.startswith(str(MeowCommand.FACT)):
        logger.info(message)
        await message.channel.send(meow_say(meow_fact()))

    elif "meow" in message.content.lower():
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

    application.add_handler(CommandHandler(MeowCommand.PETROL.value, telegram_petrol))
    application.add_handler(CommandHandler(MeowCommand.SAY.value, telegram_say))
    application.add_handler(CommandHandler(MeowCommand.FACT.value, telegram_fact))
    application.add_handler(MessageHandler(filters.TEXT, telegram_meow))

    await application.initialize()
    await application.start()

    if application.updater:
        queue = await application.updater.start_polling()

        while True:
            update = await queue.get()
            logger.info("TG", update=update)
            queue.task_done()

async def telegram_fact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(update)

    if update.effective_chat:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            parse_mode=ParseMode.MARKDOWN,
            text=meow_say(meow_fact()),
        )


async def telegram_petrol(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(update)

    if update.effective_chat:
        for text in meowpetrol_fetch_price():
            await context.bot.send_message(chat_id=update.effective_chat.id, text=text)


async def telegram_say(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(update)

    if update.message and update.message.text and update.effective_chat:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            parse_mode=ParseMode.MARKDOWN,
            text=meow_say(update.message.text.replace("/meowsay", "").strip()),
        )


async def telegram_meow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if (
        update.message
        and update.effective_chat
        and str(MeowCommand.SAY) in (update.message.text or "")
    ):
        logger.info(update)
        await telegram_say(update, context)

    elif (
        update.message
        and update.effective_chat
        and str(MeowCommand.PETROL) in (update.message.text or "")
    ):
        logger.info(update)
        await telegram_petrol(update, context)

    elif (
        update.message
        and update.effective_chat
        and "meow" in (update.message.text or "")
    ):
        logger.info(update)
        await context.bot.send_photo(
            chat_id=update.effective_chat.id, photo=meow_fetch_photo()
        )


if __name__ == "__main__":
    load_dotenv()
    client.run(os.environ["DISCORD_TOKEN"])
