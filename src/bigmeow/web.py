import asyncio
import json
from multiprocessing.synchronize import Event
from typing import Annotated

import aiohttp
import uvicorn
from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import PlainTextResponse
from structlog.stdlib import BoundLogger
from telegram.constants import ParseMode

import bigmeow.settings as settings
from bigmeow import telegram
from bigmeow.common import get_logger
from bigmeow.meow import meow_say

app = FastAPI()


class Logger:
    def __call__(self) -> BoundLogger:
        return get_logger(__name__)


async def check_is_reachable() -> bool:
    result = False

    ping_url = f"{settings.WEBHOOK_URL}/{settings.WEB_SECRET_PING}"

    async with aiohttp.request(
        "GET",
        ping_url,
        auth=aiohttp.BasicAuth(
            settings.WEB_SECRET_PING_USER, settings.WEB_SECRET_PASSWORD
        ),
    ) as response:
        if response.status == 200 and (await response.text()).strip() == "pong":
            result = True

    return result


def check_login_is_valid(authorization: str | None) -> bool:
    result = False

    if authorization:
        auth = aiohttp.BasicAuth.decode(authorization)
        result = auth.login == settings.WEB_SECRET_PING_USER and (
            auth.password == settings.WEB_SECRET_PASSWORD
        )

    return result


async def run(exit_event: Event, logger: BoundLogger = get_logger(__name__)) -> None:
    server = uvicorn.Server(
        uvicorn.Config(
            "bigmeow.web:app",
            host="0.0.0.0",
            port=settings.WEBHOOK_PORT,
            log_level="info",
            workers=None if settings.DEBUG else 4,
            reload=settings.DEBUG,
        )
    )

    logger.info("WEB: Web server is starting")
    asyncio.create_task(server.serve())

    if await check_is_reachable():
        logger.info("WEB: Web application is up and reachable")
    else:
        raise Exception("Website is unreachable")

    await asyncio.to_thread(exit_event.wait)

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
    f"/{settings.WEB_SECRET_PING}",
    response_class=PlainTextResponse,
    include_in_schema=False,
)
async def pong_get(authorization: Annotated[str, Header()]) -> str:
    assert check_login_is_valid(authorization)  # auth check

    return "pong"


@app.post(settings.TELEGRAM_WEBHOOK, include_in_schema=False)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: Annotated[str, Header()],
    logger: BoundLogger = Depends(Logger()),
) -> None:
    if not settings.TELEGRAM_WEB_TOKEN == x_telegram_bot_api_secret_token:
        return

    logger.info("WEBHOOK: Webhook receives a telegram request")
    asyncio.create_task(
        asyncio.to_thread(
            settings.telegram_updates.put,
            await request.json(),
        )
    )


@app.post(settings.ECHO_WEBHOOK, include_in_schema=False)
async def chat_post(
    request: Request,
    x_channel: Annotated[str, Header()],
    x_destination: Annotated[str, Header()],
    logger: BoundLogger = Depends(Logger()),
) -> None:
    text = (await request.body()).decode()

    logger.info(
        "WEBHOOK: Sending chat message",
        channel=x_channel,
        destination=x_destination,
        text=text,
    )
    match x_channel:
        case "telegram":
            chat_id, message_id = json.loads(x_destination)

            asyncio.create_task(
                asyncio.to_thread(
                    settings.telegram_messages.put,
                    {
                        "text": meow_say(text),
                        "chat_id": chat_id,
                        "parse_mode": ParseMode.MARKDOWN,
                        "reply_to_message_id": message_id,
                        "allow_sending_without_reply": True,
                    },
                )
            )

        case "discord":
            channel_id, message_id = json.loads(x_destination)
            asyncio.create_task(
                asyncio.to_thread(
                    settings.discord_messages.put,
                    {
                        "content": meow_say(text),
                        "channel_id": channel_id,
                        "message_id": message_id,
                    },
                )
            )

        case _:
            raise Exception("Invalid channel")