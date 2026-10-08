import asyncio
import os
import sqlite3
from collections.abc import AsyncGenerator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from sampleapp.events import record_event


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[dict[str, Any], None]:
    db_path = os.environ["SAMPLEAPP_DB"]
    connection = sqlite3.connect(db_path)
    connection.execute("CREATE TABLE IF NOT EXISTS records (value TEXT NOT NULL)")
    connection.commit()
    connection.close()
    app.state.db_path = db_path
    record_event("startup")
    yield {"loop": asyncio.get_running_loop()}
    # Deliberately not in try/finally: pins that the runner exits the lifespan normally.
    record_event("shutdown")


app = FastAPI(lifespan=lifespan)

not_an_app = object()


def get_db(request: Request) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(request.app.state.db_path, check_same_thread=False)
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


async def get_lifespan_loop(request: Request) -> asyncio.AbstractEventLoop:
    return request.state.loop


def get_current_user(authorization: Annotated[str | None, Header()] = None) -> str:
    if authorization is None:
        raise HTTPException(status_code=401, detail="missing Authorization")
    return authorization


@app.middleware("http")
async def pass_through(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    return await call_next(request)


@app.exception_handler(LookupError)
async def handle_lookup_error(request: Request, error: Exception) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": f"conflict: {error!r}"})


@app.exception_handler(Exception)
async def handle_exception(request: Request, error: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": "internal server error"})


@app.post("/{path:path}")
def catch_all(path: str) -> None:
    raise HTTPException(status_code=418, detail=f"catch-all route handled /{path}")
