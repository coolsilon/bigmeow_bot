import asyncio
import json
import os
import threading
from functools import partial
from html import escape
from typing import Annotated, Any

import aiohttp
import structlog
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Header, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from slack_sdk.oauth import AuthorizeUrlGenerator
from slack_sdk.oauth.installation_store import FileInstallationStore, Installation
from slack_sdk.oauth.state_store import FileOAuthStateStore
from slack_sdk.signature import SignatureVerifier
from slack_sdk.web.async_client import AsyncWebClient
from telegram.constants import ParseMode

import bigmeow.settings as settings
from bigmeow.common import check_is_debug
from bigmeow.meow import meow_say

load_dotenv()

logger = structlog.get_logger()


app = FastAPI()

WEB_SECRET_PING = os.environ["WEB_SECRET_PING"]
WEB_SECRET_PASSWORD = os.environ["WEB_SECRET_PASSWORD"]
WEB_SECRET_PING_USER = "BigMeow"


async def check_is_reachable() -> bool:
    global WEB_SECRET_PING_USER, WEB_SECRET_PASSWORD

    result = False

    ping_url = f'{os.environ["WEBHOOK_URL"]}/{WEB_SECRET_PING}'

    async with aiohttp.request(
        "GET",
        ping_url,
        auth=aiohttp.BasicAuth(WEB_SECRET_PING_USER, WEB_SECRET_PASSWORD),
    ) as response:
        if response.status == 200 and (await response.text()).strip() == "pong":
            result = True

    return result


def check_login_is_valid(authorization: str | None) -> bool:
    global WEB_SECRET_PING_USER, WEB_SECRET_PASSWORD

    result = False

    if authorization:
        auth = aiohttp.BasicAuth.decode(authorization)
        result = auth.login == WEB_SECRET_PING_USER and (
            auth.password == WEB_SECRET_PASSWORD
        )

    return result


async def run(exit_event: threading.Event, logger: Any = logger) -> None:
    is_debug = check_is_debug()

    server = uvicorn.Server(
        uvicorn.Config(
            "bigmeow.web:app",
            host="0.0.0.0",
            port=int(os.environ.get("WEBHOOK_PORT", "8080")),
            log_level="info",
            workers=None if is_debug else 4,
            reload=is_debug,
        )
    )

    logger.info("WEB: Web server is starting")
    asyncio.create_task(server.serve())

    if await check_is_reachable():
        logger.info("WEB: Web application is up and reachable")
    else:
        raise Exception("Website is unreachable")

    await asyncio.to_thread(exit_event.wait)

    logger.info("WEB: Webserver is stopping")
    await server.shutdown()


#
# routes
#


@app.get("/", response_class=PlainTextResponse, include_in_schema=False)
async def index_get() -> str:
    # TODO a full website
    return "Hello world"


@app.get(
    f"/{WEB_SECRET_PING}", response_class=PlainTextResponse, include_in_schema=False
)
async def pong_get(authorization: Annotated[str, Header()]) -> str:
    assert check_login_is_valid(authorization)  # auth check

    return "pong"


@app.get("/slack/install", response_class=HTMLResponse)
async def slack_oauth_start() -> str:
    state_store = FileOAuthStateStore(
        expiration_seconds=300, base_dir=str(settings.data_path_slack)
    )

    url = AuthorizeUrlGenerator(
        client_id=os.environ["SLACK_CLIENT_ID"],
        redirect_uri=f"{os.environ['WEBHOOK_URL']}/slack/callback",
        scopes=[
            "app_mentions:read",
            "channels:history",
            "chat:write",
            "files:write",
            "incoming-webhook",
        ],
    ).generate(await state_store.async_issue())

    return f"""
    <html>
        <head>
            <title>Add to slack</title>
        </head>
        <body>
            <a href="{escape(url)}">
                <img alt=""Add to Slack"" height="40" width="139" src="https://platform.slack-edge.com/img/add_to_slack.png" srcset="https://platform.slack-edge.com/img/add_to_slack.png 1x, https://platform.slack-edge.com/img/add_to_slack@2x.png 2x" />
            </a>
        </body>
    </html
    """


@app.get("/slack/callback", response_class=PlainTextResponse)
async def slack_oauth_callback(code: str, state: str) -> str:
    store_state = FileOAuthStateStore(
        expiration_seconds=300, base_dir=str(settings.data_path_slack)
    )
    store_installation = FileInstallationStore(base_dir=str(settings.data_path_slack))

    # Verify the state parameter
    if store_state.consume(state):
        client = AsyncWebClient()  # no prepared token needed for this
        # Complete the installation by calling oauth.v2.access API method
        oauth_response = await client.oauth_v2_access(
            client_id=os.environ["SLACK_CLIENT_ID"],
            client_secret=os.environ["SLACK_SECRET_CLIENT"],
            redirect_uri=f"{os.environ['WEBHOOK_URL']}/slack/callback",
            code=code,
        )
        installed_enterprise = oauth_response.get("enterprise") or {}
        is_enterprise_install = oauth_response.get("is_enterprise_install")
        installed_team = oauth_response.get("team") or {}
        installer = oauth_response.get("authed_user") or {}
        incoming_webhook = oauth_response.get("incoming_webhook") or {}
        bot_token = oauth_response.get("access_token")
        # NOTE: oauth.v2.access doesn't include bot_id in response
        bot_id = None
        enterprise_url = None
        if bot_token is not None:
            auth_test = await client.auth_test(token=bot_token)
            bot_id = auth_test["bot_id"]
            if is_enterprise_install is True:
                enterprise_url = auth_test.get("url")

        installation = Installation(
            app_id=oauth_response.get("app_id"),
            enterprise_id=installed_enterprise.get("id"),
            enterprise_name=installed_enterprise.get("name"),
            enterprise_url=enterprise_url,
            team_id=installed_team.get("id"),
            team_name=installed_team.get("name"),
            bot_token=bot_token,
            bot_id=bot_id,
            bot_user_id=oauth_response.get("bot_user_id"),
            bot_scopes=oauth_response.get(
                "scope"
            ),  # comma-separated string # type: ignore
            user_id=installer.get("id"),  # type: ignore
            user_token=installer.get("access_token"),
            user_scopes=installer.get("scope"),  # comma-separated string # type: ignore
            incoming_webhook_url=incoming_webhook.get("url"),
            incoming_webhook_channel=incoming_webhook.get("channel"),
            incoming_webhook_channel_id=incoming_webhook.get("channel_id"),
            incoming_webhook_configuration_url=incoming_webhook.get(
                "configuration_url"
            ),
            is_enterprise_install=is_enterprise_install,
            token_type=oauth_response.get("token_type"),
        )

        # Store the installation
        store_installation.save(installation)

        return "Thanks for installing this app!"

    else:
        raise Exception(
            "Try the installation again (the state value is already expired)"
        )


@app.post("/api/slack", include_in_schema=False)
async def slack_webhook(
    request: Request,
    x_slack_signature: Annotated[str, Header()],
    x_slack_request_timestamp: Annotated[int, Header()],
    logger: Any = Header(logger, include_in_schema=False),
) -> Any:
    assert SignatureVerifier(signing_secret=os.environ["SLACK_SECRET_SIGN"]).is_valid(
        body=(await request.body()).decode(),
        timestamp=str(x_slack_request_timestamp),
        signature=x_slack_signature,
    )

    data = await request.json()

    match data["type"]:
        case "url_verification":
            return data["challenge"]

        case "event_callback" if data.get("event", {}).get("type", "") == "message":
            logger.info("WEBHOOK: Webhook receives a slack message event")

            asyncio.create_task(
                asyncio.to_thread(partial(settings.slack_updates.put, data))
            )


@app.post("/telegram", include_in_schema=False)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: Annotated[str, Header()],
    logger: Any = Header(logger, include_in_schema=False),
) -> None:
    if not settings.WEB_TELEGRAM_TOKEN == x_telegram_bot_api_secret_token:
        return

    logger.info("WEBHOOK: Webhook receives a telegram request")
    asyncio.create_task(
        asyncio.to_thread(
            partial(settings.telegram_updates.put, await request.json()),
        )
    )


@app.post("/chat", include_in_schema=False)
async def chat_post(
    request: Request,
    x_channel: Annotated[str, Header()],
    x_destination: Annotated[str, Header()],
    logger: Any = Header(logger, include_in_schema=False),
) -> None:
    text = (await request.body()).decode()

    logger.info(
        "WEBHOOK: Sending chat message",
        channel=x_channel,
        destination=x_destination,
        text=text,
    )
    match x_channel:
        case "telegram":
            chat_id, message_id = json.loads(x_destination)

            asyncio.create_task(
                asyncio.to_thread(
                    partial(
                        settings.telegram_messages.put,
                        {
                            "text": meow_say(text),
                            "chat_id": chat_id,
                            "parse_mode": ParseMode.MARKDOWN,
                            "reply_to_message_id": message_id,
                            "allow_sending_without_reply": True,
                        },
                    )
                )
            )

        case "discord":
            channel_id, message_id = json.loads(x_destination)
            asyncio.create_task(
                asyncio.to_thread(
                    partial(
                        settings.discord_messages.put,
                        {
                            "content": meow_say(text),
                            "channel_id": channel_id,
                            "message_id": message_id,
                        },
                    )
                )
            )

        case "slack":
            team_id, channel_id, message_id = json.loads(x_destination)
            asyncio.create_task(
                asyncio.to_thread(
                    partial(
                        settings.slack_messages.put,
                        {
                            "team_id": team_id,
                            "payload": {
                                "channel": channel_id,
                                "thread_ts": message_id,
                                "text": meow_say(text),
                                "reply_broadcast": True,
                            },
                        },
                    )
                )
            )

        case _:
            raise Exception("Invalid channel")
