import asyncio
import json
import queue
import threading
from contextlib import suppress
from functools import partial

from dotenv import load_dotenv
from slack_sdk.oauth.installation_store import FileInstallationStore
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


async def get_client(
    store: FileInstallationStore, team_id: str
) -> AsyncWebClient | None:
    bot = await store.async_find_bot(enterprise_id=None, team_id=team_id)

    if not bot:
        return None

    return AsyncWebClient(token=bot.bot_token)


async def run(exit_event: threading.Event) -> None:
    logger.info("SLACK: Starting")

    store_installation = FileInstallationStore(base_dir=str(settings.data_path_slack))

    asyncio.create_task(updates_consume(store_installation))
    asyncio.create_task(message_consume(store_installation))

    await asyncio.to_thread(exit_event.wait)


async def updates_consume(store: FileInstallationStore) -> None:
    while True:
        try:
            update = await asyncio.to_thread(
                partial(settings.slack_updates.get, timeout=5)
            )
        except queue.Empty:
            continue

        client = await get_client(store, update["team_id"])

        if not update["event"].get("text") or not client:
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
                        (
                            update["team_id"],
                            update["event"]["channel"],
                            update["event"]["ts"],
                        )
                    ),
                )
            )

        elif message_contains(update["event"]["text"], "meow", is_command=False):
            pass


async def message_consume(store: FileInstallationStore) -> None:
    while True:
        with suppress(queue.Empty):
            message = await asyncio.to_thread(
                partial(settings.slack_messages.get, timeout=5)
            )

            client = await get_client(store, message["team_id"])

            if not client:
                continue

            logger.info("SLACK: Processing prompt reply")
            asyncio.create_task(client.chat_postMessage(**message["payload"]))
