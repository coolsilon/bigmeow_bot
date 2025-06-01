import asyncio
import json
import queue
import threading
from contextlib import suppress
from functools import partial
from io import StringIO
from multiprocessing.synchronize import Event as Event
from typing import Any

import discord
import httpx
from discord.ext import commands
from structlog.stdlib import BoundLogger

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
    meow_remind,
    meow_say,
)
from bigmeow.settings import MeowCommand


async def on_ready(
    bot: commands.Bot, messages: queue.Queue, logger: BoundLogger
) -> None:
    logger.info("DISCORD: Ready for requests")

    if settings.DEBUG:
        user = await bot.fetch_user(settings.DISCORD_USER)

        logger.info("DISCORD: Sending up message to owner", user=settings.DISCORD_USER)
        if bot.user:
            asyncio.create_task(
                user.send(f"Bot {bot.user.mention} is up\n{meow_say('Hello~')}")
            )

    asyncio.create_task(coroutine_repeat_queue(messages_consume, bot, messages, logger))


async def run(
    sync_store: settings.SyncStore,
    logger: BoundLogger = get_logger(__name__),
) -> None:
    logger.info("DISCORD: Starting")

    bot = commands.Bot(
        "!",
        intents=discord.Intents(messages=True, message_content=True),
    )
    bot.add_listener(
        partial(on_ready, bot=bot, messages=sync_store.discord.messages, logger=logger),
        "on_ready",
    )
    bot.add_listener(
        partial(
            on_message,
            bot=bot,
            cats=sync_store.cats,
            lock=sync_store.cat_lock,
            logger=logger,
        ),
        "on_message",
    )
    bot.add_command(command_make(petrol_fetch, MeowCommand.PETROL, sync_store, logger))
    bot.add_command(command_make(say_create, MeowCommand.SAY, sync_store, logger))
    bot.add_command(command_make(think_create, MeowCommand.THINK, sync_store, logger))
    bot.add_command(command_make(prompt_create, MeowCommand.PROMPT, sync_store, logger))
    bot.add_command(
        command_make(blockedornot_fetch, MeowCommand.ISBLOCKED, sync_store, logger)
    )
    bot.add_command(command_make(fact_fetch, MeowCommand.FACT, sync_store, logger))
    bot.add_command(command_make(remind_submit, MeowCommand.REMIND, sync_store, logger))

    async with bot:
        asyncio.create_task(bot.start(settings.DISCORD_TOKEN))

        await asyncio.to_thread(sync_store.exit_event.wait)

        logger.info("DISCORD: Stopping")
        await bot.close()


async def messages_consume(
    bot: commands.Bot, messages: queue.Queue, logger: BoundLogger
) -> None:
    with suppress(queue.Empty), suppress(AssertionError):
        data = await asyncio.to_thread(
            # FIXME figure something out
            messages.get,
            timeout=settings.QUEUE_TIMEOUT,
        )

        logger.info("DISCORD: Processing messages from queue", data=data)

        try:
            channel = await bot.fetch_channel(data["channel_id"])
        except Exception as e:
            logger.error("DISCORD: Invalid channel", data=data)
            logger.exception(e)  # type: ignore

        try:
            message = await channel.fetch_message(data["message_id"])  # type: ignore
        except Exception as e:
            logger.error("DISCORD: Unable to find message to reply to", data=data)
            logger.exception(e)  # type: ignore
            message = None

        asyncio.create_task(text_send(data["content"], channel, message))


def command_make(
    func, command: MeowCommand, sync_store: settings.SyncStore, logger: BoundLogger
):
    @commands.command(command.value)
    async def inner(*args, **kwargs):
        return await func(*args, **kwargs, sync_store=sync_store, logger=logger)

    return inner


async def petrol_fetch(
    context: commands.Context, sync_store: settings.SyncStore, logger: BoundLogger
) -> None:
    logger.info("DISCORD: Received a command", message=context.message)

    async with httpx.AsyncClient() as client:
        asyncio.create_task(
            text_send(
                await meow_petrol(client, sync_store.petrol, sync_store.petrol_lock),
                context.message.channel,
                context.message,
            )
        )

async def say_create(
    context: commands.Context,
    *args: str,
    sync_store: settings.SyncStore,
    logger: BoundLogger,
) -> None:
    asyncio.create_task(
        text_send(
            meow_say(" ".join(args).strip()), context.message.channel, context.message
        )
    )


async def prompt_create(
    context: commands.Context,
    *args: str,
    sync_store: settings.SyncStore,
    logger: BoundLogger,
) -> None:
    async with httpx.AsyncClient() as client:
        await meow_prompt(
            client,
            " ".join(args).strip(),
            channel="discord",
            destination=json.dumps((context.message.channel.id, context.message.id)),
        )


async def think_create(
    context: commands.Context,
    *args: str,
    sync_store: settings.SyncStore,
    logger: BoundLogger,
) -> None:
    asyncio.create_task(
        text_send(
            meow_say(" ".join(args).strip(), is_cowthink=True),
            context.message.channel,
            context.message,
        )
    )


async def blockedornot_fetch(
    context: commands.Context,
    url: str,
    sync_store: settings.SyncStore,
    logger: BoundLogger,
) -> None:
    async with httpx.AsyncClient() as client:
        asyncio.create_task(
            text_send(
                await meow_blockedornot(client, url),
                context.message.channel,
                context.message,
            )
        )


async def fact_fetch(
    context: commands.Context, sync_store: settings.SyncStore, logger: BoundLogger
) -> None:
    async with httpx.AsyncClient() as client:
        asyncio.create_task(
            text_send(
                await meow_fact(
                    client,
                    sync_store.facts,
                    sync_store.fact_lock,
                ),
                context.message.channel,
                context.message,
            )
        )


async def remind_submit(
    context: commands.Context,
    *args: str,
    sync_store: settings.SyncStore,
    logger: BoundLogger,
) -> None:
    logger.info("DISCORD: Processing remind request", message=context.message)

    try:
        asyncio.create_task(
            text_send(
                await meow_remind(
                    " ".join(args).strip(),
                    sync_store.tasks,
                    sync_store.discord.messages,
                    lambda content: {
                        "content": content,
                        "channel_id": context.message.channel.id,
                        "message_id": context.message.id,
                    },
                ),
                context.message.channel,
                context.message,
            )
        )

    except (ValueError, AssertionError):
        asyncio.create_task(
            text_send(
                "Fail to schedule message, please check format again",
                context.message.channel,
                context.message,
            )
        )


async def on_message(
    message: discord.Message,
    bot: commands.Bot,
    cats: settings.CatCache,
    lock: threading.Lock,
    logger: BoundLogger,
) -> None:
    if message.author == bot.user:
        return
    elif (ctx := await bot.get_context(message)) and ctx.valid:
        return

    logger.info("DISCORD: Received a message", message=message)

    async with httpx.AsyncClient() as client:
        if message_contains(message.content, "meow", is_command=False):
            logger.info("DISCORD: Sending a cat photo", message=message)
            asyncio.create_task(
                message.channel.send(
                    "photo from https://cataas.com/",
                    file=discord.File(
                        await meow_fetch_photo(client, cats, lock),
                        description="photo from https://cataas.com/",
                        filename="meow.png",
                    ),
                    reference=message,
                )
            )


async def text_send(
    content: str, channel: Any, reference: discord.Message | None
) -> None:
    asyncio.create_task(
        channel.send(
            reference=reference,  # type: ignore
            **(
                {
                    "file": discord.File(
                        StringIO(content.strip("`")),  # type: ignore
                        filename="message.txt",
                    )
                }
                if len(content) > 2000
                else {"content": content}
            ),
        )
    )