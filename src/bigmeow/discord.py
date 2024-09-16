import asyncio
import json
import os
from io import StringIO

import discord
import structlog
from aiohttp import ClientSession
from dotenv import load_dotenv

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


def client_init() -> discord.Client:
    intents = discord.Intents.default()
    intents.messages = True
    intents.message_content = True
    intents.members = True
    return discord.Client(intents=discord.Intents(messages=True, message_content=True))


client = client_init()


async def run(exit_event: asyncio.Event | settings.Event) -> None:
    global client

    logger.info("DISCORD: Starting")
    asyncio.create_task(client.start(os.environ["DISCORD_TOKEN"]))

    await exit_event.wait()

    logger.info("DISCORD: Stopping")
    await client.close()


async def messages_consume() -> None:
    global client

    while data := await settings.discord_messages.get():
        logger.info("DISCORD: Processing messages from queue", data=data)

        try:
            channel = await client.fetch_channel(data["channel_id"])
        except Exception as e:
            logger.error("DISCORD: Invalid channel", data=data)
            logger.exception(e)
            continue

        try:
            message = await channel.fetch_message(data["message_id"])  # type: ignore
        except Exception:
            logger.info("DISCORD: Unable to find message to reply to", data=data)
            message = None

        asyncio.create_task(text_send(data["content"], reference=message))  # type: ignore


@client.event
async def on_message(message: discord.Message) -> None:
    if message.author == client.user:
        return

    logger.info("DISCORD: Received a message", message=message)

    async with ClientSession() as session:
        if message_contains(message.content, str(MeowCommand.PETROL)):
            asyncio.create_task(
                text_send(await meow_petrol(session), reference=message)
            )

        elif message_contains(message.content, str(MeowCommand.SAY)):
            asyncio.create_task(
                text_send(
                    meow_say(message.content.replace(str(MeowCommand.SAY), "").strip()),
                    reference=message,
                )
            )

        elif message_contains(message.content, str(MeowCommand.PROMPT)):
            await meow_prompt(
                session,
                message.content.replace(str(MeowCommand.PROMPT), "").strip(),
                channel="discord",
                destination=json.dumps((message.channel.id, message.id)),
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
            asyncio.create_task(text_send(await meow_fact(session), reference=message))

        elif message_contains(message.content, str(MeowCommand.ISBLOCKED)):
            asyncio.create_task(
                text_send(
                    await meow_blockedornot(
                        session,
                        message.content.replace(str(MeowCommand.ISBLOCKED), "").strip(),
                    ),
                    reference=message,
                )
            )

        elif message_contains(message.content, "meow", is_command=False):
            logger.info("DISCORD: Sending a cat photo", message=message)
            asyncio.create_task(
                message.channel.send(
                    "photo from https://cataas.com/",
                    file=discord.File(
                        await meow_fetch_photo(session),
                        description="photo from https://cataas.com/",
                        filename="meow.png",
                    ),
                    reference=message,
                )
            )


@client.event
async def on_ready() -> None:
    global client

    logger.info("DISCORD: Ready for requests")

    if not os.environ.get("DEBUG", "False").upper() == "TRUE":
        user = await client.fetch_user(int(os.environ["DISCORD_USER"]))

        logger.info(
            "DISCORD: Sending up message to owner", user=os.environ["DISCORD_USER"]
        )
        if client.user:
            asyncio.create_task(
                user.send(f"Bot {client.user.mention} is up\n{meow_say('Hello~')}")
            )

    asyncio.create_task(messages_consume())


async def text_send(content: str, reference: discord.Message) -> None:
    asyncio.create_task(
        reference.channel.send(
            reference=reference,
            **(
                {"file": discord.File(StringIO(content), filename="message.txt")}  # type: ignore
                if len(content) > 2000
                else {"content": content}
            ),  # type: ignore
        )
    )