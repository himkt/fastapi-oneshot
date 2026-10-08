from typing import Annotated

from fastapi import Depends
from sampleapp.events import record_event
from sampleapp.main import get_current_user


def main(user: Annotated[str, Depends(get_current_user)]) -> None:
    record_event("main")
