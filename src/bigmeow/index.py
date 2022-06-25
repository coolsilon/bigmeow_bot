import asyncio
import logging
import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

logger = logging.getLogger(__name__)


async def discord_setup():
    pass


async def telegram_setup():
    application = ApplicationBuilder().token(os.environ["TELEGRAM_TOKEN"]).build()

    application.add_handler(CommandHandler("meowpetrol", telegram_petrol))

    await application.initialize()
    await application.start()

    queue = await application.updater.start_polling()

    while True:
        update = await queue.get()
        logger.info("TG update=%s", update)
        queue.task_done()


async def telegram_petrol(update: Update, context):
    await context.bot.send_message(
        chat_id=update.effective_chat.id, text="I'm a bot, please talk to me!"
    )


async def main():
    load_dotenv()

    asyncio.gather(discord_setup(), telegram_setup())


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(telegram_setup())
