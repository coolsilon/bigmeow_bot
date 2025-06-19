import asyncio
import json
from contextlib import asynccontextmanager
from typing import Annotated

import aiohttp
import uvicorn
from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import PlainTextResponse
from structlog.stdlib import BoundLogger

from bigmeow import common, discord, settings, telegram
from bigmeow.common import get_logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not hasattr(app.state, "sync_store") and isinstance(app.state, common.SyncStore):
        raise RuntimeError("Runtime sync_store object is missing")

    yield


app = FastAPI(lifespan=lifespan)


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


async def run(
    sync_store: common.SyncStore, logger: BoundLogger = get_logger(__name__)
) -> None:
    app.state.sync_store = sync_store

    server = uvicorn.Server(
        uvicorn.Config(
            app,
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

    await asyncio.to_thread(sync_store.exit_event.wait)

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
            request.app.state.sync_store.telegram.updates.put,
            await request.json(),
        )
    )


@app.get("/api/scheduled")
async def scheduled(request: Request, logger: BoundLogger = Depends(Logger())):
    logger.info(request.app.state.sync_store.scheduled)
    return [
        {
            "id": job.id,
            "name": job.name,
            "executor": job.executor,
            "when": job.next_run_time,
        }
        for job in request.app.state.sync_store.scheduled
    ]


@app.post(settings.ECHO_WEBHOOK, include_in_schema=False)
async def echo_message(
    request: Request,
    x_echo_token: Annotated[str, Header()],
    x_channel: Annotated[str, Header()],
    x_destination: Annotated[str, Header()],
    logger: BoundLogger = Depends(Logger()),
) -> None:
    if not settings.ECHO_TOKEN == x_echo_token:
        raise Exception("Bad token")

    # FIXME need auth
    text = (await request.body()).decode()

    logger.info(
        "WEBHOOK: Sending chat message",
        channel=x_channel,
        destination=x_destination,
        text=text,
    )
    match x_channel:
        case "telegram":
            asyncio.create_task(
                telegram.message_produce(
                    text,
                    request.app.state.sync_store.telegram.messages,
                    *json.loads(x_destination),
                    logger=logger,
                )
            )

        case "discord":
            asyncio.create_task(
                discord.message_produce(
                    text,
                    request.app.state.sync_store.discord.messages,
                    *json.loads(x_destination),
                    logger=logger,
                )
            )

        case _:
            raise Exception("Invalid echo channel")
