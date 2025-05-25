import asyncio
import json
import queue
from contextlib import suppress
from dataclasses import dataclass
from functools import partial
from multiprocessing.synchronize import Event

import httpx
from httpx import AsyncClient
from structlog.stdlib import BoundLogger
from telegram import Message, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
)
from telegram.ext.filters import MessageFilter

import bigmeow.settings as settings
from bigmeow.common import (
    coroutine_repeat_queue,
    get_logger,
    message_contains,
)
from bigmeow.meow import (
    meow_blockedornot,
    meow_fact,
    meow_fetch_photo,
    meow_petrol,
    meow_prompt,
    meow_say,
)
from bigmeow.settings import MeowCommand

application = ApplicationBuilder().token(settings.TELEGRAM_TOKEN).build()

@dataclass
class Filter(MessageFilter):
    keyword: str
    is_command: bool

    def filter(self, message: Message) -> bool:
        return message_contains(message.text, self.keyword, self.is_command)


async def blockedornot_fetch(
    update: Update, context: ContextTypes.DEFAULT_TYPE, logger: BoundLogger
) -> None:
    logger.info("TELEGRAM: Processing isblocked request", update=update)

    async with httpx.AsyncClient() as client:
        if update.message and update.message.text and update.effective_chat:
            asyncio.create_task(
                context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    parse_mode=ParseMode.MARKDOWN,
                    text=await meow_blockedornot(
                        client,
                        update.message.text.replace(
                            MeowCommand.ISBLOCKED.telegram(), ""
                        )
                        .replace(str(MeowCommand.ISBLOCKED), "")
                        .strip(),
                    ),
                    reply_to_message_id=update.message.id,
                    allow_sending_without_reply=True,
                )
            )


async def fact_fetch(
    update: Update, context: ContextTypes.DEFAULT_TYPE, logger: BoundLogger
) -> None:
    logger.info("TELEGRAM: Processing fact request", update=update)

    async with httpx.AsyncClient() as client:
        if update.message and update.message.text and update.effective_chat:
            asyncio.create_task(
                context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    parse_mode=ParseMode.MARKDOWN,
                    text=await meow_fact(client),
                    reply_to_message_id=update.message.id,
                    allow_sending_without_reply=True,
                )
            )


async def meow_create(
    update: Update, context: ContextTypes.DEFAULT_TYPE, logger: BoundLogger
) -> None:
    if not (update.message and update.effective_chat):
        return

    async with AsyncClient() as client:
        logger.info("TELEGRAM: Sending a cat photo", update=update)
        asyncio.create_task(
            context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=await meow_fetch_photo(client),
                caption="photo from https://cataas.com/",
                reply_to_message_id=update.message.id,
                allow_sending_without_reply=True,
            )
        )


async def messages_consume(application: Application, logger: BoundLogger) -> None:
    with suppress(queue.Empty):
        message = await asyncio.to_thread(
            settings.telegram_messages.get,
            timeout=settings.QUEUE_TIMEOUT,
        )

        logger.info("TELEGRAM: Processing prompt reply")
        asyncio.create_task(application.bot.send_message(**message))


async def petrol_fetch(
    update: Update, context: ContextTypes.DEFAULT_TYPE, logger: BoundLogger
) -> None:
    logger.info("TELEGRAM: Processing petrol request", update=update)

    async with httpx.AsyncClient() as client:
        if update.message and update.message.text and update.effective_chat:
            asyncio.create_task(
                context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    parse_mode=ParseMode.MARKDOWN,
                    text=await meow_petrol(client),
                    reply_to_message_id=update.message.id,
                    allow_sending_without_reply=True,
                )
            )


async def run(
    exit_event: Event,
    application: Application = application,
    logger: BoundLogger = get_logger(__name__),
) -> None:
    await setup(application, logger)

    async with application:
        logger.info("TELEGRAM: Starting")
        await application.start()

        logger.info("TELEGRAM: Ready for requests")

        if settings.DEBUG:
            logger.info(
                "TELEGRAM: Sending up message to owner",
                chat_id=settings.TELEGRAM_USER,
            )
            asyncio.create_task(
                application.bot.send_message(
                    chat_id=settings.TELEGRAM_USER,
                    parse_mode=ParseMode.MARKDOWN,
                    text=meow_say("Bot is up"),
                )
            )

        asyncio.create_task(coroutine_repeat_queue(updates_consume, application))
        asyncio.create_task(
            coroutine_repeat_queue(messages_consume, application, logger)
        )

        await asyncio.to_thread(exit_event.wait)

        logger.info("TELEGRAM: Stopping")
        await application.stop()


async def setup(application: Application, logger: BoundLogger) -> None:
    logger.info("TELEGRAM: Initializing application")

    application.add_handlers(
        [
            CommandHandler(
                MeowCommand.PETROL.value, partial(petrol_fetch, logger=logger)
            ),
            MessageHandler(
                Filter(MeowCommand.PETROL.value, True),
                partial(petrol_fetch, logger=logger),
            ),
            CommandHandler(MeowCommand.SAY.value, partial(say_create, logger=logger)),
            MessageHandler(
                Filter(MeowCommand.SAY.value, True), partial(say_create, logger=logger)
            ),
            CommandHandler(
                MeowCommand.THINK.value, partial(think_create, logger=logger)
            ),
            MessageHandler(
                Filter(MeowCommand.THINK.value, True),
                partial(think_create, logger=logger),
            ),
            CommandHandler(
                MeowCommand.PROMPT.value, partial(prompt_create, logger=logger)
            ),
            MessageHandler(
                Filter(MeowCommand.PROMPT.value, True),
                partial(prompt_create, logger=logger),
            ),
            CommandHandler(MeowCommand.FACT.value, partial(fact_fetch, logger=logger)),
            MessageHandler(
                Filter(MeowCommand.FACT.value, True), partial(fact_fetch, logger=logger)
            ),
            CommandHandler(
                MeowCommand.ISBLOCKED.value, partial(blockedornot_fetch, logger=logger)
            ),
            MessageHandler(
                Filter(MeowCommand.ISBLOCKED.value, True),
                partial(blockedornot_fetch, logger=logger),
            ),
            MessageHandler(
                Filter("meow", False),
                partial(meow_create, logger=logger),
            ),
        ]
    )

    asyncio.create_task(
        application.bot.set_webhook(
            f"{settings.WEBHOOK_URL}{settings.TELEGRAM_WEBHOOK}",
            allowed_updates=Update.ALL_TYPES,
            secret_token=settings.TELEGRAM_WEB_TOKEN,
        )
    )


async def prompt_create(
    update: Update, context: ContextTypes.DEFAULT_TYPE, logger: BoundLogger
) -> None:
    logger.info("TELEGRAM: Dispatching prompt request", update=update)

    async with httpx.AsyncClient() as client:
        if update.message and update.message.text and update.effective_chat:
            await meow_prompt(
                client,
                update.message.text.replace(MeowCommand.PROMPT.telegram(), "")
                .replace(str(MeowCommand.PROMPT), "")
                .strip(),
                channel="telegram",
                destination=json.dumps((update.effective_chat.id, update.message.id)),
            )


async def say_create(
    update: Update, context: ContextTypes.DEFAULT_TYPE, logger: BoundLogger
) -> None:
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
                reply_to_message_id=update.message.id,
                allow_sending_without_reply=True,
            )
        )


async def think_create(
    update: Update, context: ContextTypes.DEFAULT_TYPE, logger: BoundLogger
) -> None:
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
                reply_to_message_id=update.message.id,
                allow_sending_without_reply=True,
            )
        )


async def updates_consume(application: Application) -> None:
    with suppress(queue.Empty):
        asyncio.create_task(
            application.update_queue.put(
                Update.de_json(
                    await asyncio.to_thread(
                        settings.telegram_updates.get,
                        timeout=settings.QUEUE_TIMEOUT,
                    ),
                    application.bot,
                )
            )
        )
