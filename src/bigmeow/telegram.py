import asyncio
import os
from tkinter import N

import aiohttp
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
from bigmeow.meow import (
    meow_blockedornot,
    meow_fact,
    meow_fetch_photo,
    meow_petrol,
    meow_prompt,
    meow_say,
)
from bigmeow.settings import MeowCommand

load_dotenv()

logger = structlog.get_logger()
application = ApplicationBuilder().token(os.environ["TELEGRAM_TOKEN"]).build()


async def blockedornot_fetch(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    logger.info(update)

    async with ClientSession() as session:
        if update.message and update.message.text and update.effective_chat:
            asyncio.create_task(
                context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    parse_mode=ParseMode.MARKDOWN,
                    text=await meow_blockedornot(
                        session,
                        update.message.text.replace(
                            MeowCommand.ISBLOCKED.telegram(), ""
                        )
                        .replace(str(MeowCommand.ISBLOCKED), "")
                        .strip(),
                    ),
                )
            )


async def fact_fetch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(update)

    async with ClientSession() as session:
        if update.effective_chat:
            asyncio.create_task(
                context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    parse_mode=ParseMode.MARKDOWN,
                    text=await meow_fact(session),
                )
            )


async def message_filter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(update)

    async with ClientSession() as session:
        if (
            update.message
            and update.effective_chat
            and str(MeowCommand.SAY) in (update.message.text or "")
        ):
            asyncio.create_task(say_create(update, context))

        elif (
            update.message
            and update.effective_chat
            and str(MeowCommand.THINK) in (update.message.text or "")
        ):
            asyncio.create_task(think_create(update, context))

        elif (
            update.message
            and update.effective_chat
            and str(MeowCommand.PROMPT) in (update.message.text or "")
        ):
            asyncio.create_task(prompt_create(update, context))

        elif (
            update.message
            and update.effective_chat
            and str(MeowCommand.PETROL) in (update.message.text or "")
        ):
            asyncio.create_task(petrol_fetch(update, context))

        elif (
            update.message
            and update.effective_chat
            and str(MeowCommand.FACT) in (update.message.text or "")
        ):
            asyncio.create_task(fact_fetch(update, context))

        elif (
            update.message
            and update.effective_chat
            and str(MeowCommand.ISBLOCKED) in (update.message.text or "")
        ):
            asyncio.create_task(blockedornot_fetch(update, context))

        elif (
            update.message
            and update.effective_chat
            and "meow" in (update.message.text or "")
        ):
            asyncio.create_task(
                context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=await meow_fetch_photo(session),
                    caption="photo from https://cataas.com/",
                )
            )


async def messages_consume(application: Application) -> None:
    while message := await settings.telegram_messages.get():
        asyncio.create_task(application.bot.send_message(**message))


async def petrol_fetch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(update)

    async with ClientSession() as session:
        if update.effective_chat:
            asyncio.create_task(
                context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    parse_mode=ParseMode.MARKDOWN,
                    text=await meow_petrol(session),
                )
            )


async def run(exit_event: asyncio.Event | settings.Event) -> None:
    global application

    application.add_handler(CommandHandler(MeowCommand.PETROL.value, petrol_fetch))
    application.add_handler(CommandHandler(MeowCommand.SAY.value, say_create))
    application.add_handler(CommandHandler(MeowCommand.THINK.value, think_create))
    application.add_handler(CommandHandler(MeowCommand.PROMPT.value, prompt_create))
    application.add_handler(CommandHandler(MeowCommand.FACT.value, fact_fetch))
    application.add_handler(
        CommandHandler(MeowCommand.ISBLOCKED.value, blockedornot_fetch)
    )
    application.add_handler(MessageHandler(filters.TEXT, message_filter))

    asyncio.create_task(
        application.bot.set_webhook(
            f'{os.environ["WEBHOOK_URL"]}/telegram',
            allowed_updates=Update.ALL_TYPES,
            secret_token=settings.SECRET_TOKEN,
        )
    )

    async with application:
        logger.info("TELEGRAM: Starting")
        await application.start()

        if not os.environ.get("DEBUG", "False").upper() == "TRUE":
            logger.info(
                "TELEGRAM: Sending up message to owner",
                chat_id=os.environ["TELEGRAM_USER"],
            )
            asyncio.create_task(
                application.bot.send_message(
                    chat_id=os.environ["TELEGRAM_USER"],
                    parse_mode=ParseMode.MARKDOWN,
                    text=meow_say("Bot is up"),
                )
            )

        asyncio.create_task(updates_consume())
        asyncio.create_task(messages_consume(application))

        await exit_event.wait()

        logger.info("TELEGRAM: Stopping")
        await application.stop()


async def prompt_create(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(update)

    if update.message and update.message.text and update.effective_chat:
        async with aiohttp.ClientSession() as session:
            await meow_prompt(
                session,
                update.message.text.replace(MeowCommand.PROMPT.telegram(), "")
                .replace(str(MeowCommand.PROMPT), "")
                .strip(),
                channel="telegram",
                destination=str(update.effective_chat.id),
            )


async def say_create(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(update)

    if update.message and update.message.text and update.effective_chat:
        asyncio.create_task(
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                parse_mode=ParseMode.MARKDOWN,
                text=meow_say(
                    update.message.text.replace(MeowCommand.SAY.telegram(), "")
                    .replace(str(MeowCommand.SAY), "")
                    .strip()
                ),
            )
        )


async def think_create(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(update)

    if update.message and update.message.text and update.effective_chat:
        asyncio.create_task(
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                parse_mode=ParseMode.MARKDOWN,
                text=meow_say(
                    update.message.text.replace(MeowCommand.THINK.telegram(), "")
                    .replace(str(MeowCommand.THINK), "")
                    .strip(),
                    is_cowthink=True,
                ),
            )
        )


async def updates_consume() -> None:
    while update_dict := await settings.telegram_updates.get():
        asyncio.create_task(
            application.update_queue.put(Update.de_json(update_dict, application.bot))
        )