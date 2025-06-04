import asyncio
import json
import queue
import threading
from contextlib import suppress
from dataclasses import dataclass
from functools import partial
from typing import Any, Callable

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

from bigmeow import common, settings
from bigmeow.common import (
    MeowCommand,
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
    meow_remind,
    meow_say,
)


@dataclass
class Filter(MessageFilter):
    keyword: str
    is_command: bool

    def filter(self, message: Message) -> bool:
        return message_contains(message.text, self.keyword, self.is_command)


async def blockedornot_fetch(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    logger: BoundLogger,
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
                        logger,
                    ),
                    reply_to_message_id=update.message.id,
                    allow_sending_without_reply=True,
                )
            )


def command_handler_pair(
    command: MeowCommand,
    handler: Callable[..., Any],
    logger: BoundLogger,
    **kwargs: Any,
) -> tuple[CommandHandler, MessageHandler]:
    return CommandHandler(
        command.value, partial(handler, logger=logger, **kwargs)
    ), MessageHandler(
        Filter(str(command), True),
        partial(handler, logger=logger, **kwargs),
    )


async def fact_fetch(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    facts: common.FactCache,
    lock: threading.Lock,
    logger: BoundLogger,
) -> None:
    logger.info("TELEGRAM: Processing fact request", update=update)

    async with httpx.AsyncClient() as client:
        if update.message and update.message.text and update.effective_chat:
            asyncio.create_task(
                context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    parse_mode=ParseMode.MARKDOWN,
                    text=await meow_fact(client, facts, lock, logger),
                    reply_to_message_id=update.message.id,
                    allow_sending_without_reply=True,
                )
            )


async def meow_create(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    cats: common.CatCache,
    lock: threading.Lock,
    logger: BoundLogger,
) -> None:
    if not (update.message and update.effective_chat):
        return

    async with AsyncClient() as client:
        logger.info("TELEGRAM: Sending a cat photo", update=update)
        asyncio.create_task(
            context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=await meow_fetch_photo(client, cats, lock, logger),
                caption="photo from https://cataas.com/",
                reply_to_message_id=update.message.id,
                allow_sending_without_reply=True,
            )
        )


async def messages_consume(
    application: Application, messages: queue.Queue, logger: BoundLogger
) -> None:
    with suppress(queue.Empty):
        message = await asyncio.to_thread(messages.get, timeout=settings.QUEUE_TIMEOUT)

        logger.info("TELEGRAM: Processing message reply")
        asyncio.create_task(application.bot.send_message(**message))


async def petrol_fetch(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    petrol: common.PetrolPrice,
    petrol_lock: threading.Lock,
    logger: BoundLogger,
) -> None:
    logger.info("TELEGRAM: Processing petrol request", update=update)

    async with httpx.AsyncClient() as client:
        if update.message and update.message.text and update.effective_chat:
            asyncio.create_task(
                context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    parse_mode=ParseMode.MARKDOWN,
                    text=await meow_petrol(client, petrol, petrol_lock, logger),
                    reply_to_message_id=update.message.id,
                    allow_sending_without_reply=True,
                )
            )


async def run(
    sync_store: common.SyncStore,
    logger: BoundLogger = get_logger(__name__),
) -> None:
    application = ApplicationBuilder().token(settings.TELEGRAM_TOKEN).build()

    await setup(application, sync_store, logger)

    async with application:
        logger.info("TELEGRAM: Starting")
        await application.start()

        logger.info("TELEGRAM: Ready for requests")

        if settings.DEBUG:
            logger.info(
                "TELEGRAM: Sending up message to owner",
                chat_id=settings.TELEGRAM_USER,
            )
            await application.bot.send_message(
                chat_id=settings.TELEGRAM_USER,
                parse_mode=ParseMode.MARKDOWN,
                text=meow_say("Bot is up"),
            )

        asyncio.create_task(
            coroutine_repeat_queue(
                updates_consume, application, sync_store.telegram.updates, logger
            )
        )
        asyncio.create_task(
            coroutine_repeat_queue(
                messages_consume, application, sync_store.telegram.messages, logger
            )
        )

        await asyncio.to_thread(sync_store.exit_event.wait)

        logger.info("TELEGRAM: Stopping")
        await application.stop()


async def setup(
    application: Application, sync_store: common.SyncStore, logger: BoundLogger
) -> None:
    logger.info("TELEGRAM: Initializing application")

    application.add_handlers(
        list(
            command_handler_pair(
                MeowCommand.PETROL,
                petrol_fetch,
                logger,
                petrol=sync_store.petrol,
                petrol_lock=sync_store.petrol_lock,
            )
            + command_handler_pair(MeowCommand.SAY, say_create, logger)
            + command_handler_pair(MeowCommand.THINK, think_create, logger)
            + command_handler_pair(MeowCommand.PROMPT, prompt_create, logger)
            + command_handler_pair(
                MeowCommand.FACT,
                fact_fetch,
                logger,
                facts=sync_store.facts,
                lock=sync_store.fact_lock,
            )
            + command_handler_pair(MeowCommand.ISBLOCKED, blockedornot_fetch, logger)
            + command_handler_pair(
                MeowCommand.REMIND,
                remind_submit,
                logger,
                tasks=sync_store.tasks,
                messages=sync_store.telegram.messages,
            )
        )
        + [
            MessageHandler(
                Filter("meow", False),
                partial(
                    meow_create,
                    logger=logger,
                    cats=sync_store.cats,
                    lock=sync_store.cat_lock,
                ),
            )
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
    update: Update,
    _context: ContextTypes.DEFAULT_TYPE,
    logger: BoundLogger,
) -> None:
    logger.info("TELEGRAM: Dispatching prompt request", update=update)

    async with httpx.AsyncClient() as client:
        if update.message and update.message.text and update.effective_chat:
            await meow_prompt(
                client,
                update.message.text.replace(MeowCommand.PROMPT.telegram(), "")
                .replace(str(MeowCommand.PROMPT), "")
                .strip(),
                "telegram",
                json.dumps((update.effective_chat.id, update.message.id)),
                logger,
            )


async def say_create(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    logger: BoundLogger,
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


async def remind_submit(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    tasks: queue.Queue,
    messages: queue.Queue,
    logger: BoundLogger,
) -> None:
    logger.info("TELEGRAM: Processing remind request", update=update)

    try:
        assert update.message and update.message.text and update.effective_chat

        asyncio.create_task(
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                parse_mode=ParseMode.MARKDOWN,
                text=await meow_remind(
                    update.message.text.replace(MeowCommand.REMIND.telegram(), "")
                    .replace(str(MeowCommand.REMIND), "")
                    .strip(),
                    tasks,
                    messages,
                    lambda content: {
                        "text": content,
                        "chat_id": update.effective_chat.id,  # type: ignore
                        "parse_mode": ParseMode.MARKDOWN,
                        "reply_to_message_id": update.message.id,  # type: ignore
                        "allow_sending_without_reply": True,
                    },
                    logger,
                ),
                reply_to_message_id=update.message.id,
                allow_sending_without_reply=True,
            )
        )

    except (ValueError, AssertionError) as e:
        logger.exception(e)  # type: ignore
        asyncio.create_task(
            context.bot.send_message(
                chat_id=update.effective_chat.id,  # type: ignore
                parse_mode=ParseMode.MARKDOWN,
                text="Fail to schedule message, please check format again",
                reply_to_message_id=update.message.id,  # type: ignore
                allow_sending_without_reply=True,
            )
        )


async def think_create(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    logger: BoundLogger,
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


async def updates_consume(
    application: Application, updates: queue.Queue, logger: BoundLogger
) -> None:
    with suppress(queue.Empty):
        asyncio.create_task(
            application.update_queue.put(
                Update.de_json(
                    await asyncio.to_thread(
                        updates.get,
                        timeout=settings.QUEUE_TIMEOUT,
                    ),
                    application.bot,
                )
            )
        )
