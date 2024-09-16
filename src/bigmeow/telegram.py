import asyncio
import os

import aiohttp
import structlog
from aiohttp import ClientSession
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
from bigmeow.common import message_contains
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
    logger.info("TELEGRAM: Processing isblocked request", update=update)

    if update.message and update.message.text and update.effective_chat:
        async with ClientSession() as session:
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
    logger.info("TELEGRAM: Processing fact request", update=update)

    if update.effective_chat:
        async with ClientSession() as session:
            asyncio.create_task(
                context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    parse_mode=ParseMode.MARKDOWN,
                    text=await meow_fact(session),
                )
            )


async def message_filter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not (update.message and update.effective_chat):
        return

    logger.info("TELEGRAM: Received an update", update=update)

    if message_contains(update.message.text, str(MeowCommand.SAY)):
        asyncio.create_task(say_create(update, context))

    elif message_contains(update.message.text, str(MeowCommand.THINK)):
        asyncio.create_task(think_create(update, context))

    elif message_contains(update.message.text, str(MeowCommand.PROMPT)):
        asyncio.create_task(prompt_create(update, context))

    elif message_contains(update.message.text, str(MeowCommand.PETROL)):
        asyncio.create_task(petrol_fetch(update, context))

    elif message_contains(update.message.text, str(MeowCommand.FACT)):
        asyncio.create_task(fact_fetch(update, context))

    elif message_contains(update.message.text, str(MeowCommand.ISBLOCKED)):
        asyncio.create_task(blockedornot_fetch(update, context))

    elif message_contains(update.message.text, "meow", is_command=False):
        logger.info("TELEGRAM: Sending a cat photo", update=update)
        async with ClientSession() as session:
            asyncio.create_task(
                context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=await meow_fetch_photo(session),
                    caption="photo from https://cataas.com/",
                )
            )


async def messages_consume() -> None:
    global application

    while message := await settings.telegram_messages.get():
        asyncio.create_task(application.bot.send_message(**message))


async def petrol_fetch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("TELEGRAM: Processing petrol request", update=update)

    if update.effective_chat:
        async with ClientSession() as session:
            asyncio.create_task(
                context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    parse_mode=ParseMode.MARKDOWN,
                    text=await meow_petrol(session),
                )
            )


async def run(exit_event: asyncio.Event | settings.Event) -> None:
    global application

    await setup()

    async with application:
        logger.info("TELEGRAM: Starting")
        await application.start()

        logger.info("TELEGRAM: Ready for requests")

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
        asyncio.create_task(messages_consume())

        await exit_event.wait()

        logger.info("TELEGRAM: Stopping")
        await application.stop()


async def setup() -> None:
    global application

    logger.info("TELEGRAM: Initializing application")

    application.add_handlers(
        [
            CommandHandler(MeowCommand.PETROL.value, petrol_fetch),
            CommandHandler(MeowCommand.SAY.value, say_create),
            CommandHandler(MeowCommand.THINK.value, think_create),
            CommandHandler(MeowCommand.PROMPT.value, prompt_create),
            CommandHandler(MeowCommand.FACT.value, fact_fetch),
            CommandHandler(MeowCommand.ISBLOCKED.value, blockedornot_fetch),
            MessageHandler(filters.TEXT, message_filter),
        ]
    )

    asyncio.create_task(
        application.bot.set_webhook(
            f'{os.environ["WEBHOOK_URL"]}/telegram',
            allowed_updates=Update.ALL_TYPES,
            secret_token=settings.SECRET_TOKEN,
        )
    )


async def prompt_create(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("TELEGRAM: Dispatching prompt request", update=update)

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
    logger.info("TELEGRAM: Processing say request", update=update)

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
    logger.info("TELEGRAM: Processing think request", update=update)

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
