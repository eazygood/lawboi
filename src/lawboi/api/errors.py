from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from lawboi.domain.errors import (
    NoSourcesFoundError, UnsupportedModelError, NoModelConfiguredError, ContentBlockedError,
)

_STATUS = {
    NoSourcesFoundError: 422,
    UnsupportedModelError: 400,
    NoModelConfiguredError: 503,
    ContentBlockedError: 400,
}


def register_exception_handlers(app: FastAPI) -> None:
    for exc_type, status in _STATUS.items():
        app.add_exception_handler(exc_type, _make_handler(status))


def _make_handler(status: int):
    async def handler(request: Request, exc: Exception):
        return JSONResponse(status_code=status, content={"detail": str(exc)})
    return handler
