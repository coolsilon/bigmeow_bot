import asyncio
import logging
import threading
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any, Awaitable

import structlog


@asynccontextmanager
async def async_lock(lock: threading.Lock):
    await asyncio.to_thread(lock.acquire)

    try:
        yield
    finally:
        lock.release()


def message_contains(message: str | None, content: str, is_command=True) -> bool:
    message = message or ""

    return (message.startswith(content)) if is_command else (content in message.lower())

async def coroutine_repeat_queue(
    coro_func: Callable[..., Awaitable[None]], *args: Any
) -> None:
    try:
        while True:
            await coro_func(*args)
    except asyncio.CancelledError:
        pass


def get_logger(module_name: str) -> structlog.stdlib.BoundLogger:
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
    )
    return structlog.get_logger().bind(module=module_name)