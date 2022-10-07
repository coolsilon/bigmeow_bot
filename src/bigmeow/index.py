import logging
import os

import dateparser
import discord
import lxml.html
import requests
from dotenv import load_dotenv
from lxml.cssselect import CSSSelector
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

logger = logging.getLogger(__name__)

client = discord.Client()


def meowpetrol_fetch_date(result):
    message = None

    if result:
        dates = result[0].text.split("-")

        if dates[0].strip().isdigit():
            dates[0] = "{}{}".format(
                dates[0].strip(), " ".join(dates[1].strip().split(" ")[1:])
            )

        dates = map(dateparser.parse, dates)

        message = "From {}".format(
            " to ".join(map(lambda x: x.__format__("%d/%m/%Y"), dates))
        )

    return message


def meowpetrol_fetch_price():
    result = []
    result.append(
        "Request received, fetching and parsing data from https://hargapetrol.my/"
    )

    response = requests.get(
        "https://hargapetrol.my/",
        headers={
            "User-Agent": os.environ.get(
                "BOT_AGENT",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.12; rv:58.0) Gecko/20100101 Firefox/58.0",
            )
        },
    )

    result.append(
        meowpetrol_fetch_date(
            CSSSelector("div.starter-template > p.lead b i")(
                lxml.html.fromstring(response.text)
            ),
        )
    )

    for block in CSSSelector("div[itemprop=priceComponent]")(
        lxml.html.fromstring(response.text)
    )[:3]:
        result.append(
            "Price of {} is RM {} per litre ({} from last week)".format(
                CSSSelector("div")(block)[1].text.strip(),
                CSSSelector("span[itemprop=price]")(block)[0].text.strip(),
                CSSSelector("div")(block)[3].text.replace(" ", ""),
            )
        )

    return filter(lambda message: message is not None, result)


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content.startswith("!meowpetrol"):
        messages = meowpetrol_fetch_price()

        for text in messages:
            await message.channel.send(text)


@client.event
async def on_ready():
    """
    Get telegram setup done here
    """
    application = ApplicationBuilder().token(os.environ["TELEGRAM_TOKEN"]).build()

    application.add_handler(CommandHandler("meowpetrol", telegram_petrol))

    await application.initialize()
    await application.start()

    queue = await application.updater.start_polling()

    while True:
        update = await queue.get()
        logger.info("TG update=%s", update)
        queue.task_done()


async def telegram_petrol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    messages = meowpetrol_fetch_price()

    for text in messages:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text)


if __name__ == "__main__":
    load_dotenv()
    client.run(os.environ["DISCORD_TOKEN"])
