from unittest.mock import MagicMock, patch

import httpx
import pytest
from structlog.stdlib import BoundLogger


@pytest.fixture(name="logger")
def logger_fixture():
    yield MagicMock(spec=BoundLogger)


@pytest.fixture(name="HttpxClient")
def httpx_client():
    with patch("bigmeow.discord.httpx.AsyncClient", spec=httpx.AsyncClient) as Client:
        yield Client
