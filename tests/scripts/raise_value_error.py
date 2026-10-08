from sampleapp.events import record_event


def main() -> None:
    record_event("main")
    raise ValueError("value error raised by main")
