import os
from pathlib import Path


def record_event(name: str) -> None:
    with Path(os.environ["SAMPLEAPP_EVENTS"]).open("a") as events:
        events.write(f"{name}\n")
