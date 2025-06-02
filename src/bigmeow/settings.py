from ast import literal_eval
from os import environ

import pytz
from dotenv import load_dotenv

load_dotenv()

try:
    DEBUG = literal_eval(environ.get("DEBUG", "False"))
except Exception:
    DEBUG = False

QUEUE_TIMEOUT = int(environ.get("QUEUE_TIMEOUT", 5))

WEBHOOK_URL = environ.get("WEBHOOK_URL", "http://localhost:8000/webhook")
WEBHOOK_PORT = int(environ.get("WEBHOOK_PORT") or "8080")

WEB_SECRET_PING = environ["WEB_SECRET_PING"]
WEB_SECRET_PASSWORD = environ["WEB_SECRET_PASSWORD"]
WEB_SECRET_PING_USER = "BigMeow"

CACHE_LIMIT = 5
DATE_FORMAT = "%d/%m/%Y"

TELEGRAM_WEBHOOK = "/webhook/telegram"
TELEGRAM_USER = environ["TELEGRAM_USER"]
TELEGRAM_TOKEN = environ["TELEGRAM_TOKEN"]
TELEGRAM_WEB_TOKEN = environ["WEB_TELEGRAM_TOKEN"]

DISCORD_TOKEN = environ["DISCORD_TOKEN"]
DISCORD_USER = int(environ["DISCORD_USER"])

ECHO_WEBHOOK = "/webhook/echo"

TASK_DEFAULT_STORE = "default"
TASK_DEFAULT_EXECUTOR = "default"

TIMEZONE = pytz.utc

DATABASE_URL = environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://dbadmin:abc123@localhost:5432/bigmeow",
)

IFTTT_KEY = environ.get("IFTTT_KEY")