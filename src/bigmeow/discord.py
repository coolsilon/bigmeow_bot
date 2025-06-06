import asyncio
import json
import queue
import threading
from contextlib import suppress
from functools import partial
from io import StringIO
from multiprocessing.synchronize import Event as Event
from types import SimpleNamespace
from typing import Any, Callable

import discord
import httpx
from discord.ext import commands
from structlog.stdlib import BoundLogger

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


async def on_ready(
    bot: commands.Bot, messages: queue.Queue, logger: BoundLogger
) -> None:
    if settings.DEBUG:
        user = await bot.fetch_user(settings.DISCORD_USER)

        logger.info("DISCORD: Sending up message to owner", user=settings.DISCORD_USER)
        if bot.user:
            asyncio.create_task(
                user.send(f"Bot {bot.user.mention} is up\n{meow_say('Hello~')}")
            )

    logger.info("DISCORD: Ready for requests")
    asyncio.create_task(coroutine_repeat_queue(messages_consume, bot, messages, logger))


async def run(
    sync_store: common.SyncStore,
    logger: BoundLogger = get_logger(__name__),
) -> None:
    bot = commands.Bot(
        "!",
        intents=discord.Intents(messages=True, message_content=True),
    )

    setup(bot, sync_store, logger)

    async with bot:
        logger.info("DISCORD: Starting")
        asyncio.create_task(bot.start(settings.DISCORD_TOKEN))

        await asyncio.to_thread(sync_store.exit_event.wait)

        logger.info("DISCORD: Stopping")
        await bot.close()


def setup(bot: commands.Bot, sync_store: common.SyncStore, logger: BoundLogger) -> None:
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
    bot.add_command(
        command_make(
            MeowCommand.PETROL,
            petrol_fetch,
            logger,
            petrol=sync_store.petrol,
            lock=sync_store.petrol_lock,
        )
    )
    bot.add_command(command_make(MeowCommand.SAY, say_create, logger))
    bot.add_command(command_make(MeowCommand.THINK, think_create, logger))
    bot.add_command(command_make(MeowCommand.PROMPT, prompt_create, logger))
    bot.add_command(command_make(MeowCommand.ISBLOCKED, blockedornot_fetch, logger))
    bot.add_command(
        command_make(
            MeowCommand.FACT,
            fact_fetch,
            logger,
            facts=sync_store.facts,
            lock=sync_store.fact_lock,
        )
    )
    bot.add_command(
        command_make(
            MeowCommand.REMIND,
            remind_submit,
            logger,
            tasks=sync_store.tasks,
            messages=sync_store.discord.messages,
        )
    )


def command_make(
    command: MeowCommand, func: Callable[..., Any], logger: BoundLogger, **kwargs: Any
):
    return commands.command(command.value, extras=dict(logger=logger, **kwargs))(func)


async def message_produce(
    message: str, queue: queue.Queue, channel_id, message_id, logger: BoundLogger
):
    asyncio.create_task(
        asyncio.to_thread(
            queue.put,
            {
                "content": meow_say(message),
                "channel_id": channel_id,
                "message_id": message_id,
            },
        )
    )


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


async def petrol_fetch(context: commands.Context) -> None:
    assert context.command

    extras = SimpleNamespace(**context.command.extras)
    extras.logger.info("DISCORD: Received a command", message=context.message)

    async with httpx.AsyncClient() as client:
        asyncio.create_task(
            text_send(
                await meow_petrol(
                    client,
                    extras.petrol,
                    extras.lock,
                    extras.logger,
                ),
                context.message.channel,
                context.message,
            )
        )


async def say_create(context: commands.Context, *args: str) -> None:
    asyncio.create_task(
        text_send(
            meow_say(" ".join(args).strip()),
            context.message.channel,
            context.message,
        )
    )


async def prompt_create(context: commands.Context, *args: str) -> None:
    assert context.command

    extras = SimpleNamespace(**context.command.extras)

    async with httpx.AsyncClient() as client:
        await meow_prompt(
            client,
            " ".join(args).strip(),
            channel="discord",
            destination=json.dumps((context.message.channel.id, context.message.id)),
            logger=extras.logger,
        )


async def think_create(context: commands.Context, *args: str) -> None:
    asyncio.create_task(
        text_send(
            meow_say(" ".join(args).strip(), is_cowthink=True),
            context.message.channel,
            context.message,
        )
    )


async def blockedornot_fetch(context: commands.Context, url: str) -> None:
    assert context.command

    extras = SimpleNamespace(**context.command.extras)

    async with httpx.AsyncClient() as client:
        asyncio.create_task(
            text_send(
                await meow_blockedornot(client, url, extras.logger),
                context.message.channel,
                context.message,
            )
        )


async def fact_fetch(context: commands.Context) -> None:
    assert context.command

    extras = SimpleNamespace(**context.command.extras)

    async with httpx.AsyncClient() as client:
        asyncio.create_task(
            text_send(
                await meow_fact(
                    client,
                    extras.facts,
                    extras.lock,
                    extras.logger,
                ),
                context.message.channel,
                context.message,
            )
        )


async def remind_submit(context: commands.Context, *args: str) -> None:
    assert context.command

    extras = SimpleNamespace(**context.command.extras)
    extras.logger.info("DISCORD: Processing remind request", message=context.message)

    try:
        asyncio.create_task(
            text_send(
                meow_say(
                    await meow_remind(
                        " ".join(args).strip(),
                        extras.tasks,
                        extras.logger,
                        message_produce,
                        extras.messages,
                        context.message.channel.id,
                        context.message.id,
                    )
                ),
                context.message.channel,
                context.message,
            )
        )

    except (ValueError, AssertionError) as e:
        extras.logger.exception(e)  # type: ignore
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
    cats: common.CatCache,
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
                        await meow_fetch_photo(client, cats, lock, logger),
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
