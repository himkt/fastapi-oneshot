from fastapi import FastAPI

from sampleapp.events import record_event

legacy_app = FastAPI()


@legacy_app.on_event("startup")
def on_startup() -> None:
    record_event("startup")


@legacy_app.on_event("shutdown")
def on_shutdown() -> None:
    record_event("shutdown")
