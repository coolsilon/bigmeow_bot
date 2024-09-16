def message_contains(message: str | None, content: str, is_command=True) -> bool:
    message = message or ""

    return (message.startswith(content)) if is_command else (content in message.lower())
