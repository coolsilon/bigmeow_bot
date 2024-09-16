from os import environ

from dotenv import load_dotenv

load_dotenv()


def check_is_debug():
    return environ.get("DEBUG", "False").upper() == "TRUE"


def message_contains(message: str | None, content: str, is_command=True) -> bool:
    message = message or ""

    return (message.startswith(content)) if is_command else (content in message.lower())
