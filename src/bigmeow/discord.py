import asyncio
import os

import discord
import structlog
from aiohttp import ClientSession
from dotenv import load_dotenv

from bigmeow.meow import meow_fact, meow_fetch_photo, meow_say, meowpetrol_fetch_price
from bigmeow.settings import MeowCommand

load_dotenv()
logger = structlog.get_logger()


def discord_init_client() -> discord.Client:
    intents = discord.Intents.default()
    intents.messages = True
    intents.message_content = True
    return discord.Client(intents=discord.Intents(messages=True, message_content=True))


discord_client = discord_init_client()


async def discord_run():
    global discord_client

    try:
        logger.info("DISCORD: Starting")
        await discord_client.start(os.environ["DISCORD_TOKEN"])

    except asyncio.CancelledError:
        if not discord_client.is_closed():
            logger.info("DISCORD: Stopping")
            await discord_client.close()

            logger.info("DISCORD: Stopped")


@discord_client.event
async def on_message(message) -> None:
    if message.author == discord_client.user:
        return

    async with ClientSession() as session:
        if message.content.startswith(str(MeowCommand.PETROL)):
            logger.info(message)
            async for text in meowpetrol_fetch_price(session):
                await message.channel.send(text)

        elif message.content.startswith(str(MeowCommand.SAY)):
            logger.info(message)
            await message.channel.send(
                meow_say(message.content.replace(str(MeowCommand.SAY), "").strip())
            )

        elif message.content.startswith(str(MeowCommand.FACT)):
            logger.info(message)
            await message.channel.send(meow_say(await meow_fact(session)))

        elif "meow" in message.content.lower():
            logger.info(message)
            await message.channel.send(
                "photo from https://cataas.com/",
                file=discord.File(
                    await meow_fetch_photo(session),
                    description="photo from https://cataas.com/",
                    filename="meow.png",
                ),
            )