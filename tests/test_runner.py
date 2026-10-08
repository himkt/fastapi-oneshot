import pytest
import sampleapp.main
from fastapi import FastAPI

import fastapi_oneshot
from fastapi_oneshot.runner import ScriptExit, ScriptLoadError, get_argv, load_app


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
    with pytest.raises(ScriptLoadError):
        load_app("sampleapp.main:no_such_attribute")


def test_load_app_rejects_non_fastapi_attribute() -> None:
    with pytest.raises(ScriptLoadError, match="--app must point to a FastAPI instance"):
        load_app("sampleapp.main:not_an_app")


def test_load_app_propagates_missing_module_imported_by_the_app() -> None:
    with pytest.raises(ModuleNotFoundError) as excinfo:
        load_app("sampleapp.broken:app")
    assert not isinstance(excinfo.value, ScriptLoadError)
    assert excinfo.value.name == "oneshot_missing_dependency"
