from typing import Annotated

from fastapi import Depends
from sampleapp.events import record_event
from sampleapp.main import app, get_current_user

app.dependency_overrides[get_current_user] = lambda: "oneshot-user"


def main(user: Annotated[str, Depends(get_current_user)]) -> None:
    print(user)
    record_event("main")
