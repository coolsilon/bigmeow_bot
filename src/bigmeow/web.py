import asyncio
import os
import secrets

import structlog
from aiohttp import BasicAuth, ClientSession, web
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application

import bigmeow.settings as settings

load_dotenv()

logger = structlog.get_logger()

SECRET_PING = secrets.token_hex(128)
SECRET_PING_USER = "BigMeow"

secret_ping_password = None


def check_login(authorization: str | None) -> bool:
    global SECRET_PING_USER, secret_ping_password

    result = False

    if authorization:
        auth = BasicAuth.decode(authorization)
        result = auth.login == SECRET_PING_USER and (
            auth.password == secret_ping_password
        )

    return result


def web_init(telegram_application: Application) -> web.Application:
    routes = web.RouteTableDef()

    @routes.get("/")
    async def hello(request: web.Request) -> web.Response:
        return web.Response(text="Hello, world")

    @routes.get(f"/{SECRET_PING}")
    async def pong(request: web.Request) -> web.Response:
        assert check_login(request.headers.get("Authorization"))  # auth check

        return web.Response(text="pong")

    @routes.post("/telegram")
    async def web_telegram(request: web.Request) -> web.Response:
        nonlocal telegram_application

        assert (
            settings.SECRET_TOKEN == request.headers["X-Telegram-Bot-Api-Secret-Token"]
        )

        update = Update.de_json(await request.json(), telegram_application.bot)

        logger.info("INCOMING: Webhook receives a telegram request", update=update)
        asyncio.create_task(telegram_application.update_queue.put(update))

        return web.Response()

    application = web.Application()
    application.add_routes(routes)

    return application


async def web_run(exit_event: asyncio.Event, application: web.Application) -> None:
    logger.info("WEBHOOK: Starting", url=os.environ["WEBHOOK_URL"])
    web_runner = web.AppRunner(application)
    await web_runner.setup()

    web_site = web.TCPSite(web_runner, port=8080)
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