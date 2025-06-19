# BigMeow bot

A dumb experimental bot done for no good reason

## Invite live bot

* On discord: https://discord.com/oauth2/authorize?client_id=990077535066935357
* On telegram: https://t.me/bigmeow_bot

## What can BigMeow do?

* `!meowsay message`: your message will be repeated by a cute cat.
* `!meowthink message`: your message will be thought by a cute cat.
* `!meowpetrol`: BigMeow will attempt to report the current petrol price in Malaysia, data from https://data.gov.my/data-catalogue/fuelprice
* `!meowfact`: Return a meow fact from https://github.com/wh-iterabb-it/meowfacts
* `!meowisblocked domain.tld`: Perform a query to https://blockedornot.sinarproject.org/ to check if a domain is blocked in Malaysia
* `!meowprompt prompt`: a reply to the supplied prompt, powered by https://ifttt.com/
* `!meowremind text @ when`: Set a reminder for yourself after the time specified
* If your message has a `meow` in it, a cat photo is fetched from https://cataas.com/

NOTE: all `!` commands can be replaced by `/` in telegram, e.g. `/meowsay hello world`.

## Running bigmeow

### Docker

You can pull an image from https://hub.docker.com/r/jeffrey04/bigmeow_bot and supply the following environment variables to run the container.

```
DISCORD_TOKEN=<DISCORD TOKEN>
DISCORD_USER=<OWNER DISCORD ID>

TELEGRAM_TOKEN=<TELEGRAM TOKEN>
TELEGRAM_USER=<OWNER TELEGRAM CHAT ID>
TELEGRAM_WEB_TOKEN=<TOKEN FOR TELEGRAM WEBHOOK REQUEST>

ECHO_TOKEN=<TOKEN FOR WEB ECHO REQUEST>

WEBHOOK_URL=<URL TO WEBHOOK>

WEB_SECRET_PING=<SECRET PING WEBHOOK TO FOR UPTIME CHECK>
WEB_EECRET_PASSWORD=<TOKEN FOR SECRET PING WEBHOOK>

DEBUG=<True IF RUNNING LOCALLY OTHERWISE False>

IFTTT_KEY=<IFTTT_TOKEN>

DATABASE_URL=postgresql+psycopg://<DATABASE_USER>:<DATABASE_PASSWORD>@<DATABASE_HOST>:<DATABASE_PORT>/<DATABASE_NAME>
```

### Python

Project is developed with Python 3.11, and is managed by poetry. Refer to the previous section, and prepare a `.env` file in the base project folder to populate the environment variables. Once prepared, install the project with

```
$ poetry install
```

Then run it with

```
$ poetry run python -m bigmeow.main
```

Optionally, you can run the application with the following options:

* `--notg` to run without a telegram bot
* `--nodiscord` to run without a discord bot