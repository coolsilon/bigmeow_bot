import asyncio
import os

import discord
import structlog
from aiohttp import ClientSession
from dotenv import load_dotenv

from bigmeow.meow import (
    meow_fact,
    meow_fetch_photo,
    meow_petrol,
    meow_say,
)
from bigmeow.settings import MeowCommand

load_dotenv()
logger = structlog.get_logger()


def discord_init_client() -> discord.Client:
    intents = discord.Intents.default()
    intents.messages = True
    intents.message_content = True
    intents.members = True
    return discord.Client(intents=discord.Intents(messages=True, message_content=True))


client = discord_init_client()


async def discord_run(exit_event: asyncio.Event):
    global client

    logger.info("DISCORD: Starting")
    asyncio.create_task(client.start(os.environ["DISCORD_TOKEN"]))

    await exit_event.wait()

    logger.info("DISCORD: Stopping")
    await client.close()


@client.event
async def on_message(message) -> None:
    if message.author == client.user:
        return

    async with ClientSession() as session:
        if message.content.startswith(str(MeowCommand.PETROL)):
            logger.info(message)
            asyncio.create_task(message.channel.send(await meow_petrol(session)))

        elif message.content.startswith(str(MeowCommand.SAY)):
            logger.info(message)
            asyncio.create_task(
                message.channel.send(
                    meow_say(message.content.replace(str(MeowCommand.SAY), "").strip())
                )
            )

        elif message.content.startswith(str(MeowCommand.FACT)):
            logger.info(message)
            asyncio.create_task(message.channel.send(await meow_fact(session)))

        elif "meow" in message.content.lower():
            logger.info(message)
            asyncio.create_task(
                message.channel.send(
                    "photo from https://cataas.com/",
                    file=discord.File(
                        await meow_fetch_photo(session),
                        description="photo from https://cataas.com/",
                        filename="meow.png",
                    ),
                )
            )


@client.event
async def on_ready() -> None:
    global client

    if not os.environ.get("DEBUG", "False").upper() == "TRUE":
        user = await client.fetch_user(int(os.environ["DISCORD_USER"]))

        logger.info(
            "DISCORD: Sending up message to owner", user=os.environ["DISCORD_USER"]
        )
        if client.user:
            asyncio.create_task(
                user.send(f"Bot {client.user.mention} is up\n{meow_say('Hello~')}")
            )