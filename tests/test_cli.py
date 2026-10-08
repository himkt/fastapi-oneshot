import json
import shutil
import sqlite3
from pathlib import Path

import pytest
from conftest import TESTS_DIR, RunCli

APP = "sampleapp.main:app"
GUARDED_APP = "sampleapp.guarded:guarded_app"
LEGACY_APP = "sampleapp.legacy:legacy_app"


def read_events(events_path: Path) -> list[str]:
    return events_path.read_text().splitlines()


def read_records(db_path: Path) -> list[str]:
    connection = sqlite3.connect(db_path)
    try:
        return [value for (value,) in connection.execute("SELECT value FROM records")]
    finally:
        connection.close()


def test_success_exits_0_and_commits_the_db_write(
    run_cli: RunCli, sampleapp_db: Path, sampleapp_events: Path
) -> None:
    result = run_cli("scripts/db_write.py", "--app", APP)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert read_records(sampleapp_db) == ["db_write"]
    assert read_events(sampleapp_events) == ["startup", "main", "shutdown"]


def test_oneshot_route_wins_over_the_catch_all_route(
    run_cli: RunCli, sampleapp_events: Path
) -> None:
    result = run_cli("scripts/db_write.py", "--app", APP)
    assert result.returncode == 0, result.stderr
    assert "catch-all" not in result.stderr
    assert "main" in read_events(sampleapp_events)


def test_value_error_exits_1_with_traceback_through_exception_handler(
    run_cli: RunCli, sampleapp_events: Path
) -> None:
    result = run_cli("scripts/raise_value_error.py", "--app", APP)
    assert result.returncode == 1
    assert "Traceback (most recent call last)" in result.stderr
    assert "ValueError: value error raised by main" in result.stderr
    assert "request failed with status" not in result.stderr
    assert read_events(sampleapp_events) == ["startup", "main", "shutdown"]


def test_key_error_handled_as_409_exits_1_with_status_message(
    run_cli: RunCli, sampleapp_events: Path
) -> None:
    result = run_cli("scripts/raise_key_error.py", "--app", APP)
    assert result.returncode == 1
    assert result.stderr.startswith("fastapi-oneshot: request failed with status 409\n")
    assert "key-error-raised-by-main" in result.stderr
    assert "Traceback" not in result.stderr
    assert read_events(sampleapp_events) == ["startup", "shutdown"]


def test_missing_authorization_exits_1_with_exact_two_line_stderr(
    run_cli: RunCli, sampleapp_events: Path
) -> None:
    result = run_cli("scripts/user_missing.py", "--app", APP)
    assert result.returncode == 1
    assert result.stderr == (
        "fastapi-oneshot: request failed with status 401\n"
        '{"detail":"missing Authorization"}\n'
    )
    assert read_events(sampleapp_events) == ["startup", "shutdown"]


def test_overridden_header_dependency_exits_0(
    run_cli: RunCli, sampleapp_events: Path
) -> None:
    result = run_cli("scripts/user_overridden.py", "--app", APP)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "oneshot-user\n"
    assert read_events(sampleapp_events) == ["startup", "main", "shutdown"]


def test_plain_parameter_exits_1_with_422_message(run_cli: RunCli) -> None:
    result = run_cli("scripts/plain_parameter.py", "--app", APP)
    assert result.returncode == 1
    assert result.stderr.startswith("fastapi-oneshot: request failed with status 422\n")
    assert '"count"' in result.stderr


def test_system_exit_3_exits_3_after_lifespan_shutdown(
    run_cli: RunCli, sampleapp_events: Path
) -> None:
    result = run_cli("scripts/exit_three.py", "--app", APP)
    assert result.returncode == 3, result.stderr
    assert read_events(sampleapp_events) == ["startup", "main", "shutdown"]


def test_system_exit_none_exits_0(run_cli: RunCli, sampleapp_events: Path) -> None:
    result = run_cli("scripts/exit_none.py", "--app", APP)
    assert result.returncode == 0, result.stderr
    assert read_events(sampleapp_events) == ["startup", "shutdown"]


def test_system_exit_message_exits_1_with_message_on_stderr(
    run_cli: RunCli, sampleapp_events: Path
) -> None:
    result = run_cli("scripts/exit_message.py", "--app", APP)
    assert result.returncode == 1
    assert "exit message from main" in result.stderr
    assert read_events(sampleapp_events) == ["startup", "shutdown"]


def test_non_serializable_return_value_exits_0(run_cli: RunCli) -> None:
    result = run_cli("scripts/return_unserializable.py", "--app", APP)
    assert result.returncode == 0, result.stderr


def test_returned_500_response_is_discarded_and_exits_0(run_cli: RunCli) -> None:
    result = run_cli("scripts/return_response.py", "--app", APP)
    assert result.returncode == 0, result.stderr


def test_script_import_error_exits_1_with_traceback_and_no_lifespan(
    run_cli: RunCli, sampleapp_events: Path
) -> None:
    result = run_cli("scripts/import_error.py", "--app", APP)
    assert result.returncode == 1
    assert "Traceback (most recent call last)" in result.stderr
    assert "RuntimeError: script failed at import time" in result.stderr
    assert not sampleapp_events.exists()


def test_app_import_error_exits_1_with_traceback(run_cli: RunCli) -> None:
    result = run_cli("scripts/db_write.py", "--app", "sampleapp.broken:app")
    assert result.returncode == 1
    assert "Traceback (most recent call last)" in result.stderr
    assert "oneshot_missing_dependency" in result.stderr


@pytest.mark.parametrize(
    "script",
    [
        "scripts/missing_main.py",
        "scripts/generator_main.py",
        "scripts/callable_instance.py",
    ],
)
def test_rejected_main_shape_exits_2_without_lifespan(
    run_cli: RunCli, sampleapp_events: Path, script: str
) -> None:
    result = run_cli(script, "--app", APP)
    assert result.returncode == 2
    assert "usage:" in result.stderr
    assert not sampleapp_events.exists()


def test_extensionless_script_exits_2(
    run_cli: RunCli, sampleapp_events: Path, tmp_path: Path
) -> None:
    script = tmp_path / "db_write"
    shutil.copyfile(TESTS_DIR / "scripts" / "db_write.py", script)
    result = run_cli(str(script), "--app", APP)
    assert result.returncode == 2
    assert "usage:" in result.stderr
    assert "script must be a .py file" in result.stderr
    assert not sampleapp_events.exists()


def test_directory_script_exits_2(
    run_cli: RunCli, sampleapp_events: Path, tmp_path: Path
) -> None:
    directory = tmp_path / "not_a_script.py"
    directory.mkdir()
    result = run_cli(str(directory), "--app", APP)
    assert result.returncode == 2
    assert "usage:" in result.stderr
    assert "is not a file" in result.stderr
    assert not sampleapp_events.exists()


def test_missing_script_path_exits_2(run_cli: RunCli, sampleapp_events: Path) -> None:
    result = run_cli("scripts/no_such_script.py", "--app", APP)
    assert result.returncode == 2
    assert "usage:" in result.stderr
    assert "is not a file" in result.stderr
    assert not sampleapp_events.exists()


@pytest.mark.parametrize(
    ("app_spec", "message"),
    [
        ("sampleapp.main", "--app must be in MODULE:ATTR form"),
        ("sampleapp.no_such_module:app", "cannot import module"),
        ("sampleapp.main:no_such_attribute", "has no attribute 'no_such_attribute'"),
        ("sampleapp.main:not_an_app", "--app must point to a FastAPI instance"),
    ],
)
def test_invalid_app_exits_2(
    run_cli: RunCli, sampleapp_events: Path, app_spec: str, message: str
) -> None:
    result = run_cli("scripts/db_write.py", "--app", app_spec)
    assert result.returncode == 2
    assert "usage:" in result.stderr
    assert message in result.stderr
    assert not sampleapp_events.exists()


@pytest.mark.parametrize(
    "args",
    [
        ("--app", APP),
        ("scripts/db_write.py",),
        (),
    ],
)
def test_argparse_usage_error_exits_2(run_cli: RunCli, args: tuple[str, ...]) -> None:
    result = run_cli(*args)
    assert result.returncode == 2
    assert "usage:" in result.stderr


def test_guarded_app_without_override_exits_1_with_403_message(
    run_cli: RunCli,
) -> None:
    result = run_cli("scripts/guarded_missing.py", "--app", GUARDED_APP)
    assert result.returncode == 1
    assert result.stderr.startswith("fastapi-oneshot: request failed with status 403\n")
    assert "missing X-API-Key" in result.stderr
    assert "guarded main ran" not in result.stdout


def test_guarded_app_with_override_exits_0(run_cli: RunCli) -> None:
    result = run_cli("scripts/guarded_overridden.py", "--app", GUARDED_APP)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "guarded main ran\n"


def test_async_main_runs_on_lifespan_loop_in_main_thread(
    run_cli: RunCli, sampleapp_events: Path
) -> None:
    result = run_cli("scripts/async_lifespan_loop.py", "--app", APP)
    assert result.returncode == 0, result.stderr
    assert read_events(sampleapp_events) == ["startup", "main", "shutdown"]


def test_legacy_on_event_handlers_run_around_main(
    run_cli: RunCli, sampleapp_events: Path
) -> None:
    result = run_cli("scripts/legacy_main.py", "--app", LEGACY_APP)
    assert result.returncode == 0, result.stderr
    assert read_events(sampleapp_events) == ["startup", "main", "shutdown"]


def test_script_imports_sibling_helper_module(run_cli: RunCli) -> None:
    result = run_cli("scripts/sibling_import.py", "--app", APP)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "hello from the sibling helper\n"


def test_script_with_future_annotations_exits_0(
    run_cli: RunCli, sampleapp_db: Path
) -> None:
    result = run_cli("scripts/future_annotations.py", "--app", APP, "--", "x")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == ["x"]
    assert read_records(sampleapp_db) == ["future_annotations"]


def test_script_defining_pydantic_models_exits_0(run_cli: RunCli) -> None:
    result = run_cli("scripts/pydantic_models.py", "--app", APP)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"name": "widget", "tags": [{"label": "blue"}]}


def test_args_after_double_dash_reach_main_verbatim(run_cli: RunCli) -> None:
    script_argv = ["--dry-run", "-n", "5", "positional", "--", "--app", "other:app"]
    result = run_cli("scripts/db_write.py", "--app", APP, "--", *script_argv)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == script_argv


def test_options_before_script_and_double_dash_split(run_cli: RunCli) -> None:
    result = run_cli("--app", APP, "scripts/db_write.py", "--", "-v")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == ["-v"]


def test_empty_argv_without_double_dash(run_cli: RunCli) -> None:
    result = run_cli("scripts/db_write.py", "--app", APP)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []


def test_empty_argv_with_trailing_double_dash(run_cli: RunCli) -> None:
    result = run_cli("scripts/db_write.py", "--app", APP, "--")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []


def test_app_resolves_from_the_current_working_directory(run_cli: RunCli) -> None:
    result = run_cli("scripts/db_write.py", "--app", APP, cwd=TESTS_DIR)
    assert result.returncode == 0, result.stderr


def test_app_is_not_importable_outside_the_current_working_directory(
    run_cli: RunCli, tmp_path: Path
) -> None:
    script = TESTS_DIR / "scripts" / "db_write.py"
    result = run_cli(str(script), "--app", APP, cwd=tmp_path)
    assert result.returncode == 2
    assert "cannot import module 'sampleapp.main'" in result.stderr
