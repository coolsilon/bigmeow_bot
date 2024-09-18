import asyncio
import json
import os
from typing import Annotated

import aiohttp
import structlog
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Header, Request
from fastapi.responses import PlainTextResponse
from telegram.constants import ParseMode

import bigmeow.settings as settings
from bigmeow.common import check_is_debug
from bigmeow.meow import meow_say

load_dotenv()

logger = structlog.get_logger()


app = FastAPI()

WEB_SECRET_PING = os.environ["WEB_SECRET_PING"]
WEB_SECRET_PASSWORD = os.environ["WEB_SECRET_PASSWORD"]
WEB_SECRET_PING_USER = "BigMeow"


async def check_is_reachable() -> bool:
    global WEB_SECRET_PING_USER, WEB_SECRET_PASSWORD

    result = False

    ping_url = f'{os.environ["WEBHOOK_URL"]}/{WEB_SECRET_PING}'

    async with aiohttp.request(
        "GET",
        ping_url,
        auth=aiohttp.BasicAuth(WEB_SECRET_PING_USER, WEB_SECRET_PASSWORD),
    ) as response:
        if response.status == 200 and (await response.text()).strip() == "pong":
            result = True

    return result


def check_login_is_valid(authorization: str | None) -> bool:
    global WEB_SECRET_PING_USER, WEB_SECRET_PASSWORD

    result = False

    if authorization:
        auth = aiohttp.BasicAuth.decode(authorization)
        result = auth.login == WEB_SECRET_PING_USER and (
            auth.password == WEB_SECRET_PASSWORD
        )

    return result


async def run(exit_event: settings.PEvent) -> None:
    is_debug = check_is_debug()

    server = uvicorn.Server(
        uvicorn.Config(
            "bigmeow.web:app",
            host="0.0.0.0",
            port=int(os.environ.get("WEBHOOK_PORT", "8080")),
            log_level="info",
            workers=None if is_debug else 4,
            reload=is_debug,
        )
    )

    logger.info("WEB: Web server is starting")
    asyncio.create_task(server.serve())

    if await check_is_reachable():
        logger.info("WEB: Web application is up and reachable")
    else:
        raise Exception("Website is unreachable")

    await exit_event.wait()

    logger.info("WEB: Webserver is stopping")
    await server.shutdown()


#
# routes
#


@app.get("/", response_class=PlainTextResponse, include_in_schema=False)
async def index_get() -> str:
    # TODO a full website
    return "Hello world"


@app.get(
    f"/{WEB_SECRET_PING}", response_class=PlainTextResponse, include_in_schema=False
)
async def pong_get(authorization: Annotated[str, Header()]) -> str:
    assert check_login_is_valid(authorization)  # auth check

    return "pong"


@app.post("/telegram", include_in_schema=False)
async def telegram_post(
    request: Request, x_telegram_bot_api_secret_token: Annotated[str, Header()]
) -> None:
    if not settings.WEB_TELEGRAM_TOKEN == x_telegram_bot_api_secret_token:
        return

    logger.info("WEBHOOK: Webhook receives a telegram request")
    asyncio.create_task(settings.telegram_updates.put(await request.json()))


@app.post("/chat", include_in_schema=False)
async def chat_post(
    request: Request,
    x_channel: Annotated[str, Header()],
    x_destination: Annotated[str, Header()],
) -> None:
    text = (await request.body()).decode()

    logger.info(
        "Sending chat message",
        channel=x_channel,
        destination=x_destination,
        text=text,
    )
    match x_channel:
        case "telegram":
            chat_id, message_id = json.loads(x_destination)

            asyncio.create_task(
                settings.telegram_messages.put(
                    {
                        "text": meow_say(text),
                        "chat_id": chat_id,
                        "parse_mode": ParseMode.MARKDOWN,
                        "reply_to_message_id": message_id,
                        "allow_sending_without_reply": True,
                    }
                )
            )

        case "discord":
            channel_id, message_id = json.loads(x_destination)
            asyncio.create_task(
                settings.discord_messages.put(
                    {
                        "content": meow_say(text),
                        "channel_id": channel_id,
                        "message_id": message_id,
                    }
                )
            )

        case _:
            raise Exception("Invalid channel")
