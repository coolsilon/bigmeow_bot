import asyncio
import csv
import os
import signal
from datetime import date, timedelta
from functools import reduce
from io import BytesIO, StringIO
from random import choice
from typing import AsyncGenerator, NoReturn

import discord
import structlog
from aiohttp import ClientSession
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

import bigmeow.settings as settings
from bigmeow.settings import Change, Latest, Level, MeowCommand
from bigmeow.web import web_init, web_run


def discord_init_client() -> discord.Client:
    intents = discord.Intents.default()
    intents.messages = True
    intents.message_content = True
    return discord.Client(intents=discord.Intents(messages=True, message_content=True))

async def discord_run():
    global discord_client

    try:
        await discord_client.start(os.environ["DISCORD_TOKEN"])
        logger.info("Discord bot is running")

    except asyncio.CancelledError:
        if not discord_client.is_closed():
            logger.info("Stopping discord bot")
            await discord_client.close()

            logger.info("Discord bot is terminated")


load_dotenv()


logger = structlog.get_logger()
discord_client = discord_init_client()
telegram_application = ApplicationBuilder().token(os.environ["TELEGRAM_TOKEN"]).build()

def meowpetrol_update_latest(current: Latest, incoming: Level | Change) -> Latest:
    field = None

    if isinstance(incoming, settings.Level):
        if incoming.date > current.level.date:
            field = "level"
    else:
        if incoming.date > current.change.date:
            field = "change"

    return current._replace(**{field: incoming}) if field else current  # type: ignore


async def meow_fact(session: ClientSession) -> str:
    async with session.get("https://meowfacts.herokuapp.com/") as response:
        response_data = await response.json()

        async with settings.fact_lock:
            return (
                settings.fact_cache.cache(
                    f'{response_data.get("data")[0]}\n    - https://github.com/wh-iterabb-it/meowfacts'
                )
                if response.status == 200
                else settings.fact_cache.get()
            )


async def meowpetrol_fetch_price(session: ClientSession) -> AsyncGenerator[str, None]:
    async with settings.latest_lock:
        if (settings.latest_cache.level.date + timedelta(days=6)) < date.today():
            async with session.get(
                "https://storage.data.gov.my/commodities/fuelprice.csv"
            ) as response:
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

        yield "Data sourced from https://storage.data.gov.my/commodities/fuelprice.csv"

        yield (
            f"From {settings.latest_cache.level.date.strftime(settings.DATE_FORMAT)} to "
            f"{(settings.latest_cache.level.date + timedelta(days=6)).strftime(settings.DATE_FORMAT)}"
        )

        for field in ("ron95", "ron97", "diesel"):
            yield (
                "Price of {} is RM {} per litre ({} from last week)".format(
                    {"ron95": "RON 95", "ron97": "RON 97", "diesel": "diesel"}.get(
                        field
                    ),
                    getattr(settings.latest_cache.level, field),
                    "{:+0.2f}".format(getattr(settings.latest_cache.change, field)),
                )
            )


async def meow_fetch_photo(session: ClientSession) -> BytesIO:
    async with session.get("https://cataas.com/cat/says/meow?type=square") as response:
        logger.info("Fetching cat photo from cataas.com")

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


@discord_client.event
async def on_message(message) -> None:
    if message.author == discord_client.user:
        return

    async with ClientSession() as session:
        if message.content.startswith(str(MeowCommand.PETROL)):
            logger.info(message)
            async for text in meowpetrol_fetch_price(session):
                await message.channel.send(text)

        elif message.content.startswith(str(MeowCommand.SAY)):
            logger.info(message)
            await message.channel.send(
                meow_say(message.content.replace(str(MeowCommand.SAY), "").strip())
            )

        elif message.content.startswith(str(MeowCommand.FACT)):
            logger.info(message)
            await message.channel.send(meow_say(await meow_fact(session)))

        elif "meow" in message.content.lower():
            logger.info(message)
            await message.channel.send(
                "photo from https://cataas.com/",
                file=discord.File(
                    await meow_fetch_photo(session),
                    description="photo from https://cataas.com/",
                    filename="meow.png",
                ),
            )


async def telegram_webhook() -> NoReturn:
    global telegram_application

    telegram_application.add_handler(
        CommandHandler(MeowCommand.PETROL.value, telegram_petrol)
    )
    telegram_application.add_handler(
        CommandHandler(MeowCommand.SAY.value, telegram_say)
    )
    telegram_application.add_handler(
        CommandHandler(MeowCommand.FACT.value, telegram_fact)
    )
    telegram_application.add_handler(MessageHandler(filters.TEXT, telegram_filter))

    await telegram_application.bot.set_webhook(
        f'{os.environ["WEBHOOK_URL"]}/telegram',
        allowed_updates=Update.ALL_TYPES,
        secret_token=settings.SECRET_TOKEN,
    )

    try:
        async with telegram_application:
            await telegram_application.start()
            logger.info("Telegram bot is started")

            while True:
                await asyncio.sleep(3600)

    except (RuntimeError, asyncio.CancelledError):
        if telegram_application.running:
            logger.info("Stopping telegram bot")
            await telegram_application.stop()

            logger.info("Telegram bot is terminated")


async def telegram_fact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(update)

    async with ClientSession() as session:
        if update.effective_chat:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                parse_mode=ParseMode.MARKDOWN,
                text=meow_say(await meow_fact(session)),
            )


async def telegram_petrol(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(update)

    async with ClientSession() as session:
        if update.effective_chat:
            async for text in meowpetrol_fetch_price(session):
                await context.bot.send_message(
                    chat_id=update.effective_chat.id, text=text
                )


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


async def telegram_filter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with ClientSession() as session:
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
            and str(MeowCommand.FACT) in (update.message.text or "")
        ):
            logger.info(update)
            await telegram_fact(update, context)

        elif (
            update.message
            and update.effective_chat
            and "meow" in (update.message.text or "")
        ):
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=await meow_fetch_photo(session),
                caption="photo from https://cataas.com/",
            )


async def shutdown_handler(tasks, loop: asyncio.AbstractEventLoop) -> None:
    for task in tasks:
        if task is not asyncio.current_task():
            task.cancel()


async def main(loop: asyncio.AbstractEventLoop) -> None:
    async with asyncio.TaskGroup() as tg:
        tasks = [
            tg.create_task(telegram_webhook()),
            tg.create_task(discord_run()),
            tg.create_task(web_run(web_init(telegram_application))),
        ]

        for s in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                s, lambda: asyncio.create_task(shutdown_handler(tasks, loop))
            )


if __name__ == "__main__":
    with asyncio.Runner() as runner:
        runner.run(main(runner.get_loop()))
