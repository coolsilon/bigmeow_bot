from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from structlog.stdlib import BoundLogger

from bigmeow.meow import meow_blockedornot


@pytest_asyncio.fixture(name="httpx_client")
async def httpx_client_fixture():
    with patch("httpx.AsyncClient") as client:
        client.get = AsyncMock()
        client.post = AsyncMock()

        yield client


@pytest.mark.asyncio
async def test_blockedornot(httpx_client: httpx.AsyncClient, logger: BoundLogger):
    response = MagicMock(spec=httpx.Response)
    response.json.return_value = {
        "blocked": True,
        "different_ip": True,
        "measurement": "https://example.org",
    }
    httpx_client.get.return_value = response

    result = await meow_blockedornot(httpx_client, "example.com", logger)

    assert "is blocked" in result
    assert "blockedornot.sinarproject.org" in result

    response = MagicMock(spec=httpx.Response)
    response.json.return_value = {
        "blocked": False,
        "different_ip": True,
        "measurement": "https://example.org",
    }
    httpx_client.get.return_value = response

    result = await meow_blockedornot(httpx_client, "example.net", logger)

    assert "likely safe" in result
    assert "blockedornot.sinarproject.org" in result

    response = MagicMock(spec=httpx.Response)
    response.json.return_value = {
        "blocked": False,
        "different_ip": False,
        "measurement": "https://example.org",
    }
    httpx_client.get.return_value = response

    result = await meow_blockedornot(httpx_client, "example.info", logger)

    assert "is safe" in result
    assert "blockedornot.sinarproject.org" in result
