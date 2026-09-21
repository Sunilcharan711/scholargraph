import asyncio

from starlette.types import Message, Receive, Scope, Send

from app.core.config import Settings
from app.core.upload_limit import UploadLimitMiddleware


def test_chunked_body_limit_before_multipart_parsing() -> None:
    messages: list[Message] = []
    called = False

    async def downstream(scope: Scope, receive: Receive, send: Send) -> None:
        nonlocal called
        called = True

    async def receive() -> Message:
        return {"type": "http.request", "body": b"x" * (512 * 1024), "more_body": True}

    async def send(message: Message) -> None:
        messages.append(message)

    middleware = UploadLimitMiddleware(downstream, Settings(_env_file=None, max_file_size_mb=1))
    asyncio.run(
        middleware(
            {"type": "http", "method": "POST", "path": "/api/papers/upload", "headers": []},
            receive,
            send,
        )
    )
    assert not called
    assert messages[0]["status"] == 413
