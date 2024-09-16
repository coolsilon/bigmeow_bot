import asyncio
import json
import os
import secrets
from contextlib import asynccontextmanager
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

SECRET_PING = secrets.token_hex(128)
SECRET_PING_USER = "BigMeow"

secret_ping_password = None


def check_login_is_valid(authorization: str | None) -> bool:
    global SECRET_PING_USER, secret_ping_password

    result = False

    if authorization:
        auth = aiohttp.BasicAuth.decode(authorization)
        result = auth.login == SECRET_PING_USER and (
            auth.password == secret_ping_password
        )

    return result


def run() -> None:
    is_debug = check_is_debug()

    logger.info("WEB: Web server is starting")
    uvicorn.run(
        "bigmeow.web:app",
        host="0.0.0.0",
        port=int(os.environ.get("WEBHOOK_PORT", "8080")),
        log_level="info",
        workers=None if is_debug else 4,
    )


async def check_is_reachable() -> None:
    global SECRET_PING_USER, secret_ping_password

    ping_url = f'{os.environ["WEBHOOK_URL"]}/{SECRET_PING}'
    secret_ping_password = secrets.token_hex(128)

    async with aiohttp.request(
        "GET",
        ping_url,
        auth=aiohttp.BasicAuth(SECRET_PING_USER, secret_ping_password),
    ) as response:
        if response.status == 200 and (await response.text()).strip() == "pong":
            logger.info("WEB: Website is up", ping_url=ping_url)

        else:
            raise Exception("Site is unreachable")


#
# routes
#


@app.get("/", response_class=PlainTextResponse)
async def index_get() -> str:
    return "Hello world"


@app.get(f"/{SECRET_PING}", response_class=PlainTextResponse)
async def pong_get(authorization: Annotated[str, Header()]) -> str:
    assert check_login_is_valid(authorization)  # auth check

    return "pong"


@app.post("/telegram")
async def telegram_post(
    request: Request, x_telegram_bot_api_secret_token: Annotated[str, Header()]
) -> None:
    assert settings.SECRET_TOKEN == x_telegram_bot_api_secret_token

    logger.info("WEBHOOK: Webhook receives a telegram request")
    asyncio.create_task(settings.telegram_updates.put(await request.json()))


@app.post("/chat")
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
