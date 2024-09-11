FROM debian:12-slim as builder

ENV PATH="/root/.local/bin:${PATH}" \
    POETRY_VERSION=1.8.3

WORKDIR /app
COPY . .

RUN apt-get update && \
    apt-get install --no-install-suggests --no-install-recommends --yes pipx python-is-python3 && \
    pipx install "poetry==$POETRY_VERSION" && \
    pipx inject poetry poetry-plugin-bundle && \
    poetry bundle venv --python=/usr/bin/python3 --only=main /venv

FROM gcr.io/distroless/python3-debian12

EXPOSE 8080

COPY --from=builder /venv /venv

ENTRYPOINT ["/venv/bin/python", "-m", "bigmeow.main"]
