import asyncio
import csv
import os
import secrets
from datetime import date, timedelta
from enum import Enum
from functools import reduce
from io import BytesIO, StringIO
from random import choice, randint, shuffle
from typing import Generator, NamedTuple, NoReturn

import discord
import requests
import structlog
from aiohttp import web
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

    def telegram(self) -> str:
        COMMAND_PREFIX = "/"

        return f"{COMMAND_PREFIX}{self.value}"

    def __str__(self) -> str:
        COMMAND_PREFIX = "!"

        return f"{COMMAND_PREFIX}{self.value}"


def discord_init_client() -> discord.Client:
    intents = discord.Intents.default()
    intents.messages = True
    intents.message_content = True
    return discord.Client(intents=discord.Intents(messages=True, message_content=True))

load_dotenv()

CACHE_LIMIT = 5
DATE_FORMAT = "%d/%m/%Y"
SECRET_TOKEN = secrets.token_hex(128)

logger = structlog.get_logger()
client = discord_init_client()
application = ApplicationBuilder().token(os.environ["TELEGRAM_TOKEN"]).build()
routes = web.RouteTableDef()
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
        fact_cache.cache(
            f'{response.json().get("data")[0]}\n    - https://github.com/wh-iterabb-it/meowfacts'
        )
        if response.status_code == 200
        else fact_cache.get()
    )


def meowpetrol_fetch_price() -> Generator[str, None, None]:
    global latest_cache

    if (latest_cache.level.date + timedelta(days=6)) < date.today():
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

    yield "Data sourced from https://storage.data.gov.my/commodities/fuelprice.csv"

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
            meow_say(message.content.replace(str(MeowCommand.SAY), "").strip())
        )

    elif message.content.startswith(str(MeowCommand.FACT)):
        logger.info(message)
        await message.channel.send(meow_say(meow_fact()))

    elif "meow" in message.content.lower():
        logger.info(message)
        await message.channel.send(
            "photo from https://cataas.com/",
            file=discord.File(
                meow_fetch_photo(),
                description="photo from https://cataas.com/",
                filename="meow.png",
            ),
        )


async def telegram_webhook() -> NoReturn:
    global application

    application.add_handler(CommandHandler(MeowCommand.PETROL.value, telegram_petrol))
    application.add_handler(CommandHandler(MeowCommand.SAY.value, telegram_say))
    application.add_handler(CommandHandler(MeowCommand.FACT.value, telegram_fact))
    application.add_handler(MessageHandler(filters.TEXT, telegram_meow))

    await application.bot.set_webhook(
        f'{os.environ["WEBHOOK_URL"]}/telegram',
        allowed_updates=Update.ALL_TYPES,
        secret_token=SECRET_TOKEN,
    )

    async with application:
        await application.start()

        while True:
            await asyncio.sleep(3600)


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
            text=meow_say(
                update.message.text.replace(MeowCommand.SAY.telegram(), "")
                .replace(str(MeowCommand.SAY), "")
                .strip()
            ),
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
            chat_id=update.effective_chat.id,
            photo=meow_fetch_photo(),
            caption="photo from https://cataas.com/",
        )



@routes.get("/")
async def hello(request: web.Request) -> web.Response:
    return web.Response(text="Hello, world")


@routes.post("/telegram")
async def web_telegram(request: web.Request) -> web.Response:
    global application

    assert SECRET_TOKEN == request.headers["X-Telegram-Bot-Api-Secret-Token"]

    logger.info("Webhook received a request")
    await application.update_queue.put(
        Update.de_json(await request.json(), application.bot)
    )

    return web.Response()


def web_init() -> web.Application:
    global routes

    application = web.Application()
    application.add_routes(routes)

    return application


async def web_run(application: web.Application) -> NoReturn:
    runner = web.AppRunner(application)
    await runner.setup()

    site = web.TCPSite(runner, port=8080)
    await site.start()

    while True:
        await asyncio.sleep(3600)


async def main():
    global client

    await asyncio.gather(
        web_run(web_init()),
        client.start(os.environ["DISCORD_TOKEN"]),
        telegram_webhook(),
    )


if __name__ == "__main__":
    asyncio.run(main())
