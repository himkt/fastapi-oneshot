import asyncio
import threading
from typing import Annotated

from fastapi import Depends
from sampleapp.events import record_event
from sampleapp.main import get_lifespan_loop


async def main(
    loop: Annotated[asyncio.AbstractEventLoop, Depends(get_lifespan_loop)],
) -> None:
    assert loop is asyncio.get_running_loop(), "main is not on the lifespan's loop"
    assert threading.current_thread() is threading.main_thread(), (
        "main is not running in the main thread"
    )
    record_event("main")
