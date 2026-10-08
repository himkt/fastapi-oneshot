import asyncio
import inspect
from collections.abc import Callable
from typing import Annotated, Any

import pytest
import sampleapp.main
from fastapi import Depends, FastAPI, Request

import fastapi_oneshot
from fastapi_oneshot.runner import (
    ScriptExit,
    ScriptLoadError,
    build_endpoint,
    get_argv,
    load_app,
)


def test_package_exports_only_get_argv() -> None:
    assert fastapi_oneshot.__all__ == ["get_argv"]
    assert fastapi_oneshot.get_argv is get_argv


def test_get_argv_outside_a_run_raises_runtime_error() -> None:
    with pytest.raises(
        RuntimeError,
        match=(
            "get_argv is provided by fastapi-oneshot; it is only available "
            "inside a script run with the fastapi-oneshot command"
        ),
    ):
        get_argv()


def test_script_load_error_is_an_exception() -> None:
    assert issubclass(ScriptLoadError, Exception)


def test_script_exit_is_an_exception_carrying_the_code() -> None:
    error = ScriptExit(3)
    assert isinstance(error, Exception)
    assert not isinstance(error, SystemExit)
    assert error.code == 3


def test_script_exit_keeps_non_int_codes() -> None:
    assert ScriptExit(None).code is None
    assert ScriptExit("message").code == "message"


def test_load_app_returns_the_app_instance() -> None:
    app = load_app("sampleapp.main:app")
    assert isinstance(app, FastAPI)
    assert app is sampleapp.main.app


@pytest.mark.parametrize(
    "app_spec",
    ["sampleapp.main", "sampleapp.main:", ":app", ":", ""],
)
def test_load_app_rejects_malformed_spec(app_spec: str) -> None:
    with pytest.raises(ScriptLoadError, match="--app must be in MODULE:ATTR form"):
        load_app(app_spec)


@pytest.mark.parametrize(
    ("app_spec", "module"),
    [
        ("oneshot_no_such_module:app", "oneshot_no_such_module"),
        ("sampleapp.no_such_module:app", "sampleapp.no_such_module"),
    ],
)
def test_load_app_rejects_missing_target_module(app_spec: str, module: str) -> None:
    with pytest.raises(ScriptLoadError, match=f"cannot import module '{module}'"):
        load_app(app_spec)


def test_load_app_rejects_missing_parent_package() -> None:
    with pytest.raises(
        ScriptLoadError, match="cannot import module 'oneshot_no_such_package.main'"
    ):
        load_app("oneshot_no_such_package.main:app")


def test_load_app_rejects_missing_attribute() -> None:
    with pytest.raises(ScriptLoadError, match="has no attribute 'no_such_attribute'"):
        load_app("sampleapp.main:no_such_attribute")


def test_load_app_rejects_non_fastapi_attribute() -> None:
    with pytest.raises(ScriptLoadError, match="--app must point to a FastAPI instance"):
        load_app("sampleapp.main:not_an_app")


def test_load_app_propagates_missing_module_imported_by_the_app() -> None:
    with pytest.raises(ModuleNotFoundError) as excinfo:
        load_app("sampleapp.broken:app")
    assert not isinstance(excinfo.value, ScriptLoadError)
    assert excinfo.value.name == "oneshot_missing_dependency"


def sync_main_with_dependencies(
    argv: Annotated[list[str], Depends(get_argv)],
    request: "Request",
) -> str:
    return "discarded"


async def async_main_with_dependencies(
    argv: Annotated[list[str], Depends(get_argv)],
    request: "Request",
) -> str:
    return "discarded"


@pytest.mark.parametrize(
    "main", [sync_main_with_dependencies, async_main_with_dependencies]
)
def test_build_endpoint_signature_has_resolved_parameters_and_none_return(
    main: Callable[..., Any],
) -> None:
    endpoint = build_endpoint(main)
    signature = inspect.signature(endpoint)
    expected = inspect.signature(main, eval_str=True)
    assert signature.parameters == expected.parameters
    assert signature.parameters["request"].annotation is Request
    assert signature.return_annotation is None


@pytest.mark.parametrize(
    "main", [sync_main_with_dependencies, async_main_with_dependencies]
)
def test_build_endpoint_carries_no_wrapped(main: Callable[..., Any]) -> None:
    assert not hasattr(build_endpoint(main), "__wrapped__")


def test_build_endpoint_is_sync_for_sync_main() -> None:
    assert not inspect.iscoroutinefunction(build_endpoint(sync_main_with_dependencies))


def test_build_endpoint_is_coroutine_function_for_async_main() -> None:
    assert inspect.iscoroutinefunction(build_endpoint(async_main_with_dependencies))


def test_build_endpoint_sync_passes_values_and_discards_return_value() -> None:
    received: dict[str, object] = {}

    def main(argv: list[str]) -> str:
        received["argv"] = argv
        return "discarded"

    assert build_endpoint(main)(argv=["--flag"]) is None
    assert received == {"argv": ["--flag"]}


def test_build_endpoint_async_passes_values_and_discards_return_value() -> None:
    received: dict[str, object] = {}

    async def main(argv: list[str]) -> str:
        received["argv"] = argv
        return "discarded"

    assert asyncio.run(build_endpoint(main)(argv=["--flag"])) is None
    assert received == {"argv": ["--flag"]}


def test_build_endpoint_sync_converts_system_exit_to_script_exit() -> None:
    def main() -> None:
        raise SystemExit(3)

    with pytest.raises(ScriptExit) as excinfo:
        build_endpoint(main)()
    assert excinfo.value.code == 3
    assert isinstance(excinfo.value.__cause__, SystemExit)


def test_build_endpoint_async_converts_system_exit_to_script_exit() -> None:
    async def main() -> None:
        raise SystemExit(3)

    with pytest.raises(ScriptExit) as excinfo:
        asyncio.run(build_endpoint(main)())
    assert excinfo.value.code == 3
    assert isinstance(excinfo.value.__cause__, SystemExit)


def test_build_endpoint_sync_propagates_other_exceptions_unchanged() -> None:
    def main() -> None:
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        build_endpoint(main)()


def test_build_endpoint_async_propagates_other_exceptions_unchanged() -> None:
    async def main() -> None:
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        asyncio.run(build_endpoint(main)())


def test_build_endpoint_sync_main_returning_coroutine_raises_type_error() -> None:
    async def body() -> None:
        pass

    coroutine = body()

    def main() -> object:
        return coroutine

    try:
        with pytest.raises(
            TypeError, match="main returned an awaitable; define main with async def"
        ):
            build_endpoint(main)()
    finally:
        coroutine.close()
