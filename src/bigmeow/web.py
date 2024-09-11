import asyncio
import os
import secrets

import structlog
from aiohttp import BasicAuth, ClientSession, web
from dotenv import load_dotenv

import bigmeow.settings as settings

load_dotenv()

logger = structlog.get_logger()

SECRET_PING = secrets.token_hex(128)
SECRET_PING_USER = "BigMeow"

secret_ping_password = None
routes = web.RouteTableDef()


def check_login_is_valid(authorization: str | None) -> bool:
    global SECRET_PING_USER, secret_ping_password

    result = False

    if authorization:
        auth = BasicAuth.decode(authorization)
        result = auth.login == SECRET_PING_USER and (
            auth.password == secret_ping_password
        )

    return result


async def run(exit_event: asyncio.Event | settings.Event) -> None:
    global routes

    application = web.Application()
    application.add_routes(routes)

    logger.info("WEBHOOK: Starting", url=os.environ["WEBHOOK_URL"])
    web_runner = web.AppRunner(application)
    await web_runner.setup()

    web_site = web.TCPSite(web_runner, port=int(os.environ.get("WEBHOOK_PORT", "8080")))
    await web_site.start()

    async with ClientSession() as session:
        if not await web_check(session):
            logger.error("WEBHOOK: Webhook is unreachable, stopping")

            await web_site.stop()
            await web_runner.cleanup()
            raise Exception("Webhook is unreachable")

        else:
            await exit_event.wait()

            logger.info("WEBHOOK: Stopping")
            await web_site.stop()
            await web_runner.cleanup()


async def web_check(session: ClientSession) -> bool:
    global SECRET_PING_USER, secret_ping_password

    result, ping_url = False, f'{os.environ["WEBHOOK_URL"]}/{SECRET_PING}'
    secret_ping_password = secrets.token_hex(128)

    async with session.get(
        ping_url, auth=BasicAuth(SECRET_PING_USER, secret_ping_password)
    ) as response:
        if response.status == 200 and (await response.text()).strip() == "pong":
            logger.info("WEBHOOK: Website is up", ping_url=ping_url)
            result = True

    return result


#
# routes
#


@routes.get("/")
async def index_get(request: web.Request) -> web.Response:
    return web.Response(text="Hello, world")


@routes.get(f"/{SECRET_PING}")
async def pong_get(request: web.Request) -> web.Response:
    assert check_login_is_valid(request.headers.get("Authorization"))  # auth check

    return web.Response(text="pong")


@routes.post("/telegram")
async def telegram_post(request: web.Request) -> web.Response:
    assert settings.SECRET_TOKEN == request.headers["X-Telegram-Bot-Api-Secret-Token"]

    logger.info("WEBHOOK: Webhook receives a telegram request")
    asyncio.create_task(settings.telegram_queue.put(await request.json()))

    return web.Response()
