import asyncio
import os
from typing import NoReturn

import structlog
from aiohttp import ClientSession
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import bigmeow.settings as settings
from bigmeow.meow import meow_fact, meow_fetch_photo, meow_petrol, meow_say
from bigmeow.settings import MeowCommand

load_dotenv()

logger = structlog.get_logger()
application = ApplicationBuilder().token(os.environ["TELEGRAM_TOKEN"]).build()


async def telegram_run() -> NoReturn:
    global application

    application.add_handler(CommandHandler(MeowCommand.PETROL.value, telegram_petrol))
    application.add_handler(CommandHandler(MeowCommand.SAY.value, telegram_say))
    application.add_handler(CommandHandler(MeowCommand.FACT.value, telegram_fact))
    application.add_handler(MessageHandler(filters.TEXT, telegram_filter))

    await application.bot.set_webhook(
        f'{os.environ["WEBHOOK_URL"]}/telegram',
        allowed_updates=Update.ALL_TYPES,
        secret_token=settings.SECRET_TOKEN,
    )

    try:
        async with application:
            logger.info("TELEGRAM: Starting")
            await application.start()

            if not bool(os.environ.get("DEBUG", "False")):
                logger.info(
                    "TELEGRAM: Sending up message to owner",
                    chat_id=os.environ["TELEGRAM_CHAT"],
                )
                await application.bot.send_message(
                    chat_id=os.environ["TELEGRAM_CHAT"],
                    text=meow_say(
                        f"Bot @{(await application.bot.get_me()).username} is up"
                    ),
                )

            while True:
                await asyncio.sleep(3600)

    except (RuntimeError, asyncio.CancelledError):
        if application.running:
            logger.info("TELEGRAM: Stopping")
            await application.stop()

            logger.info("TELEGRAM: Stopped")


async def telegram_fact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(update)

    async with ClientSession() as session:
        if update.effective_chat:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                parse_mode=ParseMode.MARKDOWN,
                text=await meow_fact(session),
            )


async def telegram_petrol(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(update)

    async with ClientSession() as session:
        if update.effective_chat:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                parse_mode=ParseMode.MARKDOWN,
                text=await meow_petrol(session),
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