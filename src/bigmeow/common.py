from collections.abc import Callable
from os import environ
from typing import Awaitable

from dotenv import load_dotenv

load_dotenv()


def check_is_debug():
    return environ.get("DEBUG", "False").upper() == "TRUE"


def message_contains(message: str | None, content: str, is_command=True) -> bool:
    message = message or ""

    return (message.startswith(content)) if is_command else (content in message.lower())

async def coroutine_repeat_queue(coro_func: Callable[[], Awaitable[None]]) -> None:
    while True:
        await coro_func()