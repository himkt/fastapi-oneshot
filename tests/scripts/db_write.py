import json
import sqlite3
from typing import Annotated

from fastapi import Depends
from sampleapp.events import record_event
from sampleapp.main import get_db

from fastapi_oneshot import get_argv


def main(
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    argv: Annotated[list[str], Depends(get_argv)],
) -> None:
    db.execute("INSERT INTO records (value) VALUES (?)", ("db_write",))
    print(json.dumps(argv))
    record_event("main")
