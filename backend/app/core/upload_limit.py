"""Bound multipart bodies before Starlette spools individual file parts."""

from tempfile import SpooledTemporaryFile

from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings


class UploadLimitMiddleware:
    """Bound disk/memory use for both Content-Length and chunked upload requests."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or scope.get("path", "").rstrip("/") != "/api/papers/upload"
        ):
            await self.app(scope, receive, send)
            return
        # Multipart framing gets 64 KiB; the file itself has its own exact byte limit.
        limit = self.settings.max_file_size_mb * 1024 * 1024 + 64 * 1024
        headers = dict(scope.get("headers", []))
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            await JSONResponse({"detail": "Invalid Content-Length."}, 400)(scope, receive, send)
            return
        if declared > limit:
            await JSONResponse({"detail": "Upload request is too large."}, 413)(
                scope, receive, send
            )
            return
        # Temporary spool is always closed, including client disconnect and validation failures.
        with SpooledTemporaryFile(max_size=1024 * 1024) as spool:
            total = 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body = message.get("body", b"")
                total += len(body)
                if total > limit:
                    await JSONResponse({"detail": "Upload request is too large."}, 413)(
                        scope, receive, send
                    )
                    return
                await run_in_threadpool(spool.write, body)
                if not message.get("more_body", False):
                    break
            await run_in_threadpool(spool.seek, 0)
            remaining = total

            async def replay() -> Message:
                nonlocal remaining
                if remaining == 0:
                    return {"type": "http.request", "body": b"", "more_body": False}
                data = await run_in_threadpool(spool.read, 64 * 1024)
                remaining -= len(data)
                return {"type": "http.request", "body": data, "more_body": remaining > 0}

            await self.app(scope, replay, send)
