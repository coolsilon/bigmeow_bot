FROM python:3.11-slim as base

FROM base as builder

ENV PATH="/root/.local/bin:${PATH}" \
    POETRY_VERSION=1.8.3

WORKDIR /src

COPY . .

RUN apt-get update && \
    apt-get install --no-install-suggests --no-install-recommends --yes pipx && \
    pipx install "poetry==$POETRY_VERSION" && \
    pipx inject poetry poetry-plugin-bundle && \
    poetry bundle venv --python=/usr/bin/python3 --only=main /venv

FROM base as final

EXPOSE 8080

WORKDIR /app

COPY --from=builder /venv /venv
COPY docker-entrypoint.sh .

CMD ["sh", "docker-entrypoint.sh"]
