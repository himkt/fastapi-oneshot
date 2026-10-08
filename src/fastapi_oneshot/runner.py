import asyncio
import importlib
import importlib.util
import inspect
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI
from starlette.types import Receive, Scope, Send

ROUTE_PATH = "/__fastapi_oneshot__"
SCRIPT_MODULE_NAME = "__oneshot_script__"


class ScriptLoadError(Exception):
    """The --app target or the script cannot be loaded; the CLI maps it to exit 2."""


class ScriptExit(Exception):
    """SystemExit raised by main, carried through the app as an Exception."""

    def __init__(self, code: str | int | None) -> None:
        super().__init__(code)
        self.code = code


def get_argv() -> list[str]:
    raise RuntimeError(
        "get_argv is provided by fastapi-oneshot; it is only available "
        "inside a script run with the fastapi-oneshot command"
    )


def load_app(app_spec: str) -> FastAPI:
    module_name, _, attr = app_spec.rpartition(":")
    if not module_name or not attr:
        raise ScriptLoadError("--app must be in MODULE:ATTR form")

    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as error:
        if error.name is not None and (
            module_name == error.name or module_name.startswith(error.name + ".")
        ):
            raise ScriptLoadError(f"cannot import module {module_name!r}") from error
        raise

    if not hasattr(module, attr):
        raise ScriptLoadError(f"module {module_name!r} has no attribute {attr!r}")
    app = getattr(module, attr)
    if not isinstance(app, FastAPI):
        raise ScriptLoadError("--app must point to a FastAPI instance")
    return app


def load_main(script_path: Path) -> Callable[..., Any]:
    if not script_path.is_file():
        raise ScriptLoadError(f"script {script_path} is not a file")
    spec = importlib.util.spec_from_file_location(SCRIPT_MODULE_NAME, script_path)
    if spec is None or spec.loader is None:
        raise ScriptLoadError("script must be a .py file")

    sys.path.insert(0, str(script_path.resolve().parent))
    module = importlib.util.module_from_spec(spec)
    sys.modules[SCRIPT_MODULE_NAME] = module
    spec.loader.exec_module(module)

    if not hasattr(module, "main"):
        raise ScriptLoadError(f"script {script_path} defines no main function")
    main = module.main
    if not inspect.isfunction(main):
        raise ScriptLoadError("main must be a function defined with def or async def")
    if inspect.isgeneratorfunction(main) or inspect.isasyncgenfunction(main):
        raise ScriptLoadError("main must not be a generator function")
    return main


def build_endpoint(main: Callable[..., Any]) -> Callable[..., Any]:
    signature = inspect.signature(main, eval_str=True)
    endpoint: Callable[..., Any]

    if inspect.iscoroutinefunction(main):

        async def call_async(**values: Any) -> None:
            try:
                await main(**values)
            except SystemExit as error:
                raise ScriptExit(error.code) from error

        endpoint = call_async

    else:

        def call_sync(**values: Any) -> None:
            try:
                result = main(**values)
            except SystemExit as error:
                raise ScriptExit(error.code) from error
            if inspect.isawaitable(result):
                raise TypeError(
                    "main returned an awaitable; define main with async def"
                )

        endpoint = call_sync

    setattr(endpoint, "__signature__", signature.replace(return_annotation=None))  # noqa: B010
    return endpoint


def run(app: FastAPI, script_path: Path, argv: list[str]) -> httpx.Response:
    main = load_main(script_path)

    def provide_argv() -> list[str]:
        return argv

    app.dependency_overrides[get_argv] = provide_argv
    app.add_api_route(
        ROUTE_PATH,
        build_endpoint(main),
        methods=["POST"],
        include_in_schema=False,
        response_model=None,
    )
    app.router.routes.insert(0, app.router.routes.pop())
    return asyncio.run(execute(app))


async def execute(app: FastAPI) -> httpx.Response:
    failure: Exception | None = None
    async with app.router.lifespan_context(app) as lifespan_state:
        try:
            return await post_once(app, lifespan_state)
        except Exception as error:
            failure = error
    assert failure is not None
    raise failure


async def post_once(
    app: FastAPI, lifespan_state: Mapping[str, Any] | None
) -> httpx.Response:
    async def app_with_state(scope: Scope, receive: Receive, send: Send) -> None:
        scope["state"] = dict(lifespan_state or {})
        await app(scope, receive, send)

    transport = httpx.ASGITransport(app=app_with_state)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://localhost"
    ) as client:
        return await client.post(ROUTE_PATH)
