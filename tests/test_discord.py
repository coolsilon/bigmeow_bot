import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands
from structlog.stdlib import BoundLogger

from bigmeow.discord import (
    blockedornot_fetch,
    fact_fetch,
    petrol_fetch,
    prompt_create,
    remind_submit,
    say_create,
    think_create,
)


@pytest.fixture(name="context")
def context_fixture():
    context = MagicMock(commands.Context)
    context.command = MagicMock(commands.Command)
    context.message = MagicMock(discord.Message)
    context.message.channel = MagicMock(discord.TextChannel)

    yield context


@pytest.fixture(name="text_send")
def text_send_fixture():
    with patch("bigmeow.discord.text_send") as text_send:
        yield text_send


@pytest.mark.asyncio
async def test_petrol(
    logger: BoundLogger,
    context: commands.Context,
    text_send: AsyncMock,
    HttpxClient: Any,
):
    with (
        patch("bigmeow.discord.meow_petrol") as meow_petrol,
    ):
        meow_petrol.return_value = "petrol report"

        assert context.command
        context.command.extras = {
            "logger": logger,
            "petrol": MagicMock(),
            "lock": MagicMock(),
        }

        await petrol_fetch(context)

        HttpxClient.assert_called_once()

        async with HttpxClient() as client:
            meow_petrol.assert_awaited_once_with(
                client,
                context.command.extras["petrol"],
                context.command.extras["lock"],
                logger,
            )

        text_send.assert_called_once_with(
            meow_petrol.return_value, context.message.channel, context.message
        )


@pytest.mark.asyncio
async def test_say_create(
    logger: BoundLogger, context: commands.Context, text_send: AsyncMock
):
    with patch("bigmeow.discord.meow_say") as meow_say:
        meow_say.return_value = "decorated"

        await say_create(context, "hello", "world")

        meow_say.assert_called_once_with("hello world")

        text_send.assert_called_once_with(
            meow_say.return_value, context.message.channel, context.message
        )


@pytest.mark.asyncio
async def test_think_create(
    logger: BoundLogger, context: commands.Context, text_send: AsyncMock
):
    with patch("bigmeow.discord.meow_say") as meow_say:
        meow_say.return_value = "decorated"

        await think_create(context, "hello", "world")

        meow_say.assert_called_once_with("hello world", is_cowthink=True)

        text_send.assert_called_once_with(
            meow_say.return_value, context.message.channel, context.message
        )


@pytest.mark.asyncio
async def test_prompt_create(
    logger: BoundLogger, context: commands.Context, HttpxClient: Any
):
    with patch("bigmeow.discord.meow_prompt") as meow_prompt:
        assert context.command
        context.command.extras = {"logger": logger}

        context.message.channel.id = 1
        context.message.id = 1

        await prompt_create(context, "le", "petit", "prince")

        async with HttpxClient() as client:
            meow_prompt.assert_called_once_with(
                client,
                "le petit prince",
                channel="discord",
                destination=json.dumps(
                    (context.message.channel.id, context.message.id)
                ),
                logger=logger,
            )


@pytest.mark.asyncio
async def test_blockedornot(
    logger: BoundLogger,
    context: commands.Context,
    HttpxClient: Any,
    text_send: AsyncMock,
):
    with patch("bigmeow.discord.meow_blockedornot") as meow_blockedornot:
        meow_blockedornot.return_value = "result"

        assert context.command
        context.command.extras = {"logger": logger}

        await blockedornot_fetch(context, "example.org")

        async with HttpxClient() as client:
            meow_blockedornot.assert_awaited_once_with(client, "example.org", logger)

        text_send.assert_called_once_with(
            "result", context.message.channel, context.message
        )


@pytest.mark.asyncio
async def test_fact_fetch(
    logger: BoundLogger,
    context: commands.Context,
    HttpxClient: Any,
    text_send: AsyncMock,
):
    with patch("bigmeow.discord.meow_fact") as meow_fact:
        meow_fact.return_value = "fact"

        assert context.command
        context.command.extras = {
            "logger": logger,
            "facts": MagicMock(),
            "lock": MagicMock(),
        }

        await fact_fetch(context)

        async with HttpxClient() as client:
            meow_fact.assert_awaited_once_with(
                client,
                context.command.extras["facts"],
                context.command.extras["lock"],
                logger,
            )

            text_send.assert_called_once_with(
                "fact", context.message.channel, context.message
            )


@pytest.mark.asyncio
async def test_remind_submit(
    logger: BoundLogger, context: commands.Context, text_send: AsyncMock
):
    with patch("bigmeow.discord.meow_remind") as meow_remind:
        meow_remind.return_value = "scheduled"

        assert context.command
        context.command.extras = {
            "logger": logger,
            "tasks": MagicMock(),
            "messages": MagicMock(),
        }

        await remind_submit(context, "do", "this", "@", "5", "seconds", "later")

        meow_remind.assert_awaited_once()

        assert "do this @ 5 seconds later" == meow_remind.call_args.args[0]
        assert context.command.extras["tasks"] == meow_remind.call_args.args[1]
        assert context.command.extras["messages"] == meow_remind.call_args.args[2]
        assert logger == meow_remind.call_args.args[4]

        result = meow_remind.call_args.args[3]("do this")
        expected = {
            "content": "do this",
            "channel_id": context.message.channel.id,
            "message_id": context.message.id,
        }
        assert expected == result

        text_send.assert_called_once_with(
            "scheduled", context.message.channel, context.message
        )
