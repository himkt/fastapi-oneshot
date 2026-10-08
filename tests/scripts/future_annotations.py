from __future__ import annotations

import json
import sqlite3
from typing import Annotated

from fastapi import Depends
from sampleapp.main import get_db

from fastapi_oneshot import get_argv


def main(
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    argv: Annotated[list[str], Depends(get_argv)],
) -> None:
    db.execute("INSERT INTO records (value) VALUES (?)", ("future_annotations",))
    print(json.dumps(argv))
