import asyncio
import signal

import structlog
from dotenv import load_dotenv

import bigmeow.telegram as telegram
from bigmeow.discord import discord_run
from bigmeow.telegram import telegram_run
from bigmeow.web import web_init, web_run

load_dotenv()

logger = structlog.get_logger()


async def shutdown_handler(tasks, loop: asyncio.AbstractEventLoop) -> None:
    for task in tasks:
        if task is not asyncio.current_task():
            task.cancel()


async def main(loop: asyncio.AbstractEventLoop) -> None:
    async with asyncio.TaskGroup() as tg:
        tasks = [
            tg.create_task(telegram_run()),
            tg.create_task(discord_run()),
            tg.create_task(web_run(web_init(telegram.application))),
        ]

        for s in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                s, lambda: asyncio.create_task(shutdown_handler(tasks, loop))
            )


if __name__ == "__main__":
    with asyncio.Runner() as runner:
        runner.run(main(runner.get_loop()))
