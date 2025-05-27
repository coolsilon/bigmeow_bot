import asyncio
import json
import queue
from contextlib import suppress
from io import StringIO
from multiprocessing.synchronize import Event as Event

import dateparser
import discord
import httpx
from apscheduler.triggers.date import DateTrigger
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


def client_init() -> discord.Client:
    intents = discord.Intents.default()
    intents.messages = True
    intents.message_content = True
    intents.members = True
    return discord.Client(intents=discord.Intents(messages=True, message_content=True))


client = client_init()


async def run(
    exit_event: Event,
    client: discord.Client = client,
    logger: BoundLogger = get_logger(__name__),
) -> None:
    logger.info("DISCORD: Starting")
    async with client:
        asyncio.create_task(client.start(settings.DISCORD_TOKEN))

        await asyncio.to_thread(exit_event.wait)

        logger.info("DISCORD: Stopping")
        await client.close()


async def messages_consume(client: discord.Client, logger: BoundLogger) -> None:
    with suppress(queue.Empty):
        data = await asyncio.to_thread(
            settings.discord_messages.get, timeout=settings.QUEUE_TIMEOUT
        )

        logger.info("DISCORD: Processing messages from queue", data=data)

        try:
            channel = await client.fetch_channel(data["channel_id"])
        except Exception as e:
            logger.error("DISCORD: Invalid channel", data=data)
            logger.exception(e)  # type: ignore

        try:
            message = await channel.fetch_message(data["message_id"])  # type: ignore
        except Exception:
            logger.info("DISCORD: Unable to find message to reply to", data=data)
            message = None

        asyncio.create_task(text_send(data["content"], reference=message))  # type: ignore


@client.event
async def on_message(
    message: discord.Message,
    client: discord.Client = client,
    logger: BoundLogger = get_logger(__name__),
) -> None:
    if message.author == client.user:
        return

    logger.info("DISCORD: Received a message", message=message)

    async with httpx.AsyncClient() as aclient:
        if message_contains(message.content, str(MeowCommand.PETROL)):
            asyncio.create_task(text_send(await meow_petrol(), reference=message))

        elif message_contains(message.content, str(MeowCommand.SAY)):
            asyncio.create_task(
                text_send(
                    meow_say(message.content.replace(str(MeowCommand.SAY), "").strip()),
                    reference=message,
                )
            )

        elif message_contains(message.content, str(MeowCommand.PROMPT)):
            asyncio.create_task(
                meow_prompt(
                    aclient,
                    message.content.replace(str(MeowCommand.PROMPT), "").strip(),
                    channel="discord",
                    destination=json.dumps((message.channel.id, message.id)),
                )
            )

        elif message_contains(message.content, str(MeowCommand.THINK)):
            asyncio.create_task(
                text_send(
                    meow_say(
                        message.content.replace(str(MeowCommand.THINK), "").strip(),
                        is_cowthink=True,
                    ),
                    reference=message,
                )
            )

        elif message_contains(message.content, str(MeowCommand.FACT)):
            asyncio.create_task(text_send(await meow_fact(), reference=message))

        elif message_contains(message.content, str(MeowCommand.ISBLOCKED)):
            asyncio.create_task(
                text_send(
                    await meow_blockedornot(
                        message.content.replace(str(MeowCommand.ISBLOCKED), "").strip(),
                    ),
                    reference=message,
                )
            )

        elif message_contains(message.content, str(MeowCommand.REMIND)):
            asyncio.create_task(process_remind(message, client, logger))

        elif message_contains(message.content, "meow", is_command=False):
            logger.info("DISCORD: Sending a cat photo", message=message)
            asyncio.create_task(
                message.channel.send(
                    "photo from https://cataas.com/",
                    file=discord.File(
                        await meow_fetch_photo(aclient),
                        description="photo from https://cataas.com/",
                        filename="meow.png",
                    ),
                    reference=message,
                )
            )


@client.event
async def on_ready(
    client: discord.Client = client, logger: BoundLogger = get_logger(__name__)
) -> None:
    logger.info("DISCORD: Ready for requests")

    if settings.DEBUG:
        user = await client.fetch_user(settings.DISCORD_USER)

        logger.info("DISCORD: Sending up message to owner", user=settings.DISCORD_USER)
        if client.user:
            asyncio.create_task(
                user.send(f"Bot {client.user.mention} is up\n{meow_say('Hello~')}")
            )

    asyncio.create_task(coroutine_repeat_queue(messages_consume, client, logger))


async def process_remind(
    message: discord.Message, client: discord.Client, logger: BoundLogger
) -> None:
    logger.info("DISCORD: Processing remind request", message=message)

    try:
        asyncio.create_task(
            text_send(
                await meow_remind(
                    message.content.replace(str(MeowCommand.REMIND), "").strip(),
                    settings.discord_messages,
                    lambda content: {
                        "content": content,
                        "channel_id": message.channel.id,
                        "message_id": message.id,
                    },
                ),
                reference=message,
            )
        )

    except (ValueError, AssertionError):
        asyncio.create_task(
            text_send(
                "Fail to schedule message, please check format again",
                reference=message,
            )
        )


async def text_send(content: str, reference: discord.Message) -> None:
    asyncio.create_task(
        reference.channel.send(
            reference=reference,
            **(
                {
                    "file": discord.File(
                        StringIO(content.strip("`")),  # type: ignore
                        filename="message.txt",
                    )
                }
                if len(content) > 2000
                else {"content": content}
            ),  # type: ignore
        )
    )