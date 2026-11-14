"""The contract's error envelope: every non-2xx response is {"error": {code, message, details}}."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("ghostwatch")

# Contract §0: the error code for each HTTP status a framework-raised HTTPException can carry.
_CODE_BY_STATUS = {
    400: "bad_request",
    401: "unauthorized",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
}


class ApiError(Exception):
    """An error the API returns deliberately, already expressed in contract terms."""

    def __init__(self, status_code: int, code: str, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def error_response(status_code: int, code: str, message: str, details: Any = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details}},
    )


async def _handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
    return error_response(exc.status_code, exc.code, exc.message, exc.details)


async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [{"loc": list(error["loc"]), "msg": error["msg"]} for error in exc.errors()]
    return error_response(422, "validation_error", "Request validation failed.", details)


async def _handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    fallback = "internal_error" if exc.status_code >= 500 else "bad_request"
    code = _CODE_BY_STATUS.get(exc.status_code, fallback)
    response = error_response(exc.status_code, code, str(exc.detail))
    if exc.headers:
        response.headers.update(exc.headers)
    return response


class UnhandledErrorMiddleware:
    """Turn any unhandled exception into a 500 envelope without leaking its text.

    This sits inside the CORS middleware, so the browser can read the error body. Starlette's own
    last-resort handler runs outside all user middleware and its responses carry no CORS headers.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_tracking_start(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_tracking_start)
        except Exception:
            if response_started:
                raise
            logger.exception("Unhandled error on %s %s", scope["method"], scope["path"])
            response = error_response(500, "internal_error", "Internal server error.")
            await response(scope, receive, send)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _handle_api_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(HTTPException, _handle_http_exception)


def not_found(kind: str, id_: str) -> ApiError:
    return ApiError(404, "not_found", f"{kind} {id_} does not exist.")


def invalid_query(param: str, message: str) -> ApiError:
    """A query parameter failed validation that FastAPI's own type checks cannot express."""
    return ApiError(
        422, "validation_error", "Request validation failed.", [{"loc": ["query", param], "msg": message}]
    )
