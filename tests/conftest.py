import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent

RunCli = Callable[..., subprocess.CompletedProcess[str]]


@pytest.fixture
def sampleapp_db(tmp_path: Path) -> Path:
    return tmp_path / "sampleapp.sqlite3"


@pytest.fixture
def sampleapp_events(tmp_path: Path) -> Path:
    return tmp_path / "events.log"


@pytest.fixture
def run_cli(sampleapp_db: Path, sampleapp_events: Path) -> RunCli:
    executable = Path(sys.executable).with_name("fastapi-oneshot")
    assert executable.is_file(), f"console script not found at {executable}"
    env = {
        **os.environ,
        "SAMPLEAPP_DB": str(sampleapp_db),
        "SAMPLEAPP_EVENTS": str(sampleapp_events),
    }

    def run(*args: str, cwd: Path = TESTS_DIR) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(executable), *args],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )

    return run
