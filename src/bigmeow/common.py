from collections.abc import Callable
from typing import Any, Awaitable

import structlog


def message_contains(message: str | None, content: str, is_command=True) -> bool:
    message = message or ""

    return (message.startswith(content)) if is_command else (content in message.lower())

async def coroutine_repeat_queue(
    coro_func: Callable[..., Awaitable[None]], *args: Any
) -> None:
    while True:
        await coro_func(*args)


def get_logger(module_name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger().bind(module=module_name)