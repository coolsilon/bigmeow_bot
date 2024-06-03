import asyncio
import os
import secrets
from typing import NoReturn

import structlog
from aiohttp import ClientSession, web
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application

import bigmeow.settings as settings

load_dotenv()

logger = structlog.get_logger()

SECRET_PING = secrets.token_hex(128)


def web_init(telegram_application: Application) -> web.Application:
    web_routes = web.RouteTableDef()

    @web_routes.get("/")
    async def hello(request: web.Request) -> web.Response:
        return web.Response(text="Hello, world")

    @web_routes.get(f"/{SECRET_PING}")
    async def pong(request: web.Request) -> web.Response:
        return web.Response(text="pong")

    @web_routes.post("/telegram")
    async def web_telegram(request: web.Request) -> web.Response:
        nonlocal telegram_application

        assert (
            settings.SECRET_TOKEN == request.headers["X-Telegram-Bot-Api-Secret-Token"]
        )

        update = Update.de_json(await request.json(), telegram_application.bot)

        logger.info("INCOMING: Webhook receives a telegram request", update=update)
        await telegram_application.update_queue.put(update)

        return web.Response()

    web_application = web.Application()
    web_application.add_routes(web_routes)

    return web_application


async def web_run(web_application: web.Application) -> NoReturn:
    logger.info("WEBHOOK: starting", url=os.environ["WEBHOOK_URL"])
    web_runner = web.AppRunner(web_application)
    await web_runner.setup()

    web_site = web.TCPSite(web_runner, port=8080)
    await web_site.start()


    try:
        async with ClientSession() as session:
            while True:
                if not await web_check(session):
                    await web_site.stop()
                    await web_runner.cleanup()
                    break

                await asyncio.sleep(3600)
    except asyncio.CancelledError:
        logger.info("WEBHOOK: stopping")
        await web_site.stop()
        await web_runner.cleanup()

        logger.info("WEBHOOK: stopped")


async def web_check(session: ClientSession) -> bool:
    result, ping_url = False, f'{os.environ["WEBHOOK_URL"]}/{SECRET_PING}'

    async with session.get(ping_url) as response:
        if response.status == 200 and (await response.text()).strip() == "pong":
            logger.info("WEBHOOK: website is up", ping_url=ping_url)
            result = True

    return result