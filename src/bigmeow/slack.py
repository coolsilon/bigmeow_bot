import asyncio
import json
from os import environ

from dotenv import load_dotenv
from slack_sdk.web.async_client import AsyncWebClient
from structlog import get_logger

from bigmeow import settings
from bigmeow.common import message_contains
from bigmeow.meow import (
    meow_blockedornot,
    meow_fact,
    meow_petrol,
    meow_prompt,
    meow_say,
)
from bigmeow.settings import MeowCommand

load_dotenv()

logger = get_logger()


async def run(exit_event: settings.Event) -> None:
    logger.info("SLACK: Starting")
    client = AsyncWebClient(token=environ["SLACK_TOKEN_BOT"])

    asyncio.create_task(updates_consume(client))
    asyncio.create_task(message_consume(client))

    await exit_event.wait()


async def updates_consume(client: AsyncWebClient):
    while update := await settings.slack_updates.get():
        if not update["event"].get("text"):
            continue

        if message_contains(update["event"]["text"], str(MeowCommand.SAY)):
            asyncio.create_task(
                client.chat_postMessage(
                    channel=update["event"]["channel"],
                    thread_ts=update["event"]["ts"],
                    text=meow_say(
                        update["event"]["text"]
                        .replace(str(MeowCommand.SAY), "")
                        .strip()
                    ),
                    reply_broadcast=True,
                )
            )

        elif message_contains(update["event"]["text"], str(MeowCommand.THINK)):
            asyncio.create_task(
                client.chat_postMessage(
                    channel=update["event"]["channel"],
                    thread_ts=update["event"]["ts"],
                    text=meow_say(
                        update["event"]["text"]
                        .replace(str(MeowCommand.THINK), "")
                        .strip(),
                        is_cowthink=True,
                    ),
                    reply_broadcast=True,
                )
            )

        elif message_contains(update["event"]["text"], str(MeowCommand.PETROL)):
            asyncio.create_task(
                client.chat_postMessage(
                    channel=update["event"]["channel"],
                    thread_ts=update["event"]["ts"],
                    text=await meow_petrol(),
                    reply_broadcast=True,
                )
            )

        elif message_contains(update["event"]["text"], str(MeowCommand.FACT)):
            asyncio.create_task(
                client.chat_postMessage(
                    channel=update["event"]["channel"],
                    thread_ts=update["event"]["ts"],
                    text=await meow_fact(),
                    reply_broadcast=True,
                )
            )

        elif message_contains(update["event"]["text"], str(MeowCommand.ISBLOCKED)):
            asyncio.create_task(
                client.chat_postMessage(
                    channel=update["event"]["channel"],
                    thread_ts=update["event"]["ts"],
                    text=await meow_blockedornot(
                        update["event"]["text"]
                        .replace(str(MeowCommand.ISBLOCKED), "")
                        .strip()
                        .strip("<>")
                        .split("|")[-1]
                    ),
                    reply_broadcast=True,
                )
            )

        elif message_contains(update["event"]["text"], str(MeowCommand.PROMPT)):
            asyncio.create_task(
                meow_prompt(
                    update["event"]["text"]
                    .replace(str(MeowCommand.PROMPT), "")
                    .strip(),
                    channel="slack",
                    destination=json.dumps(
                        (update["event"]["channel"], update["event"]["ts"])
                    ),
                )
            )

        elif message_contains(update["event"]["text"], "meow", is_command=False):
            pass


async def message_consume(client: AsyncWebClient) -> None:
    while message := await settings.slack_messages.get():
        logger.info("SLACK: Processing prompt reply")
        asyncio.create_task(client.chat_postMessage(**message))
