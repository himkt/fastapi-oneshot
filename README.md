# fastapi-oneshot

Run a one-shot Python script against an existing FastAPI app, so that the script's `main` function receives the app's dependencies — DB sessions, settings, clients — through ordinary `Depends`.

`fastapi-oneshot` registers `main` as a temporary path operation, enters the app's lifespan, and sends a single in-process request to it through `httpx.ASGITransport`. Dependency resolution, `yield` cleanup, `dependency_overrides` and the lifespan all work exactly as they do for a request handler, and everything runs on one event loop in the main thread.

## Installation

Install `fastapi-oneshot` into the same environment as your app, because it imports the app:

```console
uv add --dev fastapi-oneshot
```

or

```console
pip install fastapi-oneshot
```

Python 3.10 or later and FastAPI 0.115.0 or later are required.

## Usage

```console
fastapi-oneshot SCRIPT --app MODULE:ATTR [-- SCRIPT_ARG ...]
```

| Argument | Meaning |
|----------|---------|
| `SCRIPT` | Path to the script file that defines `main`. |
| `--app MODULE:ATTR` | Import string of the `FastAPI` instance, e.g. `myapp.main:app`. |
| `--` | Everything after the first `--` is passed to the script verbatim. |

Run the command from your project root: the current working directory is put on `sys.path` before `--app` is imported, as with `uvicorn` and `fastapi run`.

## Writing a script

A script is a Python file that defines a module-level function named `main`, with `def` or `async def`. Every parameter of `main` is a dependency, declared with `Depends(...)` exactly as in a path operation:

```python
# scripts/backfill.py
import argparse
import sqlite3
from typing import Annotated

from fastapi import Depends
from fastapi_oneshot import get_argv

from myapp.dependencies import get_db


def main(
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    argv: Annotated[list[str], Depends(get_argv)],
) -> None:
    parser = argparse.ArgumentParser(prog="backfill")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    ...
```

```console
fastapi-oneshot scripts/backfill.py --app myapp.main:app -- --dry-run
```

- The app's lifespan runs around `main`, so dependencies can read lifespan-initialized state through `request.app.state` and lifespan-yielded state through `request.state`.
- A sync `main` runs in FastAPI's threadpool; an async `main` runs on the main-thread event loop shared with the lifespan.
- The return value of `main` is discarded. Signal failure by raising an exception.
- The script's directory is put on `sys.path`, so the script can import sibling modules, as with `python script.py`.
- The script runs as a module named `__oneshot_script__`, so an `if __name__ == "__main__":` block does not run.

### Script arguments: `get_argv`

`fastapi_oneshot.get_argv` is a dependency that returns the arguments after `--` as `list[str]` (`[]` when there is no `--`). Parse them with `argparse` or any other parser, as in the example above.

Script options always come from `get_argv`. A plain parameter of `main` that is not a dependency is not a CLI option: a plain parameter with a default (`verbose: bool = False`) always receives its default, and a required plain parameter fails the run with a 422 validation error.

Calling `get_argv` outside a `fastapi-oneshot` run, e.g. from a normal app route, raises `RuntimeError`.

### Overriding dependencies

The request that runs `main` carries no headers, cookies, query or body. Override every dependency that reads them — such as "current user from a bearer token" — with `app.dependency_overrides` at module level in the script:

```python
from myapp.auth import get_current_user
from myapp.main import app
from myapp.models import User

app.dependency_overrides[get_current_user] = lambda: User(id=0, name="oneshot")
```

The same applies to app-level dependencies given to `FastAPI(dependencies=[...])`, such as a global authentication check: they run before `main`, so override them in the script.

Import the app through the same module path as `--app` (`from myapp.main import app` for `--app myapp.main:app`). Importing it through another path, such as `src.myapp.main`, creates a second app instance, and the override applies to that instance instead of the one that runs. Set overrides at module level: overrides set inside `main` are too late to affect `main`'s own parameters.

## Exit codes

| Outcome | Exit code |
|---------|-----------|
| `main` returns and the response is 2xx | 0 |
| An exception is raised in `main`, a dependency, the lifespan, the app import or the script import (the traceback is printed) | 1 |
| The response is not 2xx — e.g. `HTTPException`, a 422 validation error, a rejecting app-level dependency or middleware | 1 |
| `main` raises `SystemExit` (e.g. `sys.exit(3)`, `argparse` errors) | the requested status |
| The script or `--app` cannot be loaded, or `main` is missing or not a plain function | 2 |
| Missing `SCRIPT` or `--app` | 2 |

A non-2xx response is reported on stderr with its status and body:

```text
fastapi-oneshot: request failed with status 401
{"detail":"missing Authorization"}
```

Once the lifespan has started, it is shut down normally before `fastapi-oneshot` exits, whatever the outcome.

## Known limitations

- **Middleware runs.** Every app middleware processes the request, which is sent to `http://localhost/__fastapi_oneshot__`. A middleware that rejects it (e.g. authentication, `TrustedHostMiddleware` without `localhost` in `allowed_hosts`, `HTTPSRedirectMiddleware` answering 307 — redirects are not followed) results in a non-2xx exit.
- **App-level dependencies run.** Dependencies given to `FastAPI(dependencies=[...])` apply to the oneshot route, so a global authentication or rate-limit dependency runs before `main` and typically rejects the request (401/403 → exit 1). Override such a dependency in the script with `app.dependency_overrides`. Dependencies attached to an `APIRouter` do not apply, because the route is added to the app directly.
- **Request-derived dependencies.** The request carries no headers, cookies, query or body beyond httpx defaults; dependencies that read them must be overridden in the script.
- **Lifespan entered directly.** The lifespan runs through `app.router.lifespan_context(app)`, not through an ASGI `lifespan` scope, so ASGI middleware that intercepts the `lifespan` scope does not see startup and shutdown.
- **Ctrl-C.** `fastapi-oneshot` installs no signal handling of its own. On Python 3.11+, the first Ctrl-C cancels the run: `CancelledError` is raised at the current `await`, propagates through `yield`-dependency cleanup and into the lifespan, and the process ends with `KeyboardInterrupt`; a second Ctrl-C raises `KeyboardInterrupt` immediately. On Python 3.10, `KeyboardInterrupt` is raised wherever the main thread is, and the run is cancelled the same way. Lifespan shutdown code runs on this path only when it is in `try/finally`. A sync `main` running in a worker thread cannot be interrupted, and the process exits only after it returns. The exit status is Python's default for an uncaught `KeyboardInterrupt` (130 in POSIX shells). Make scripts that must stay consistent when interrupted rely on DB transactions.
- **`sys.exit()` in `main` is a failed request to the app.** `sys.exit(...)` — including `sys.exit(0)` and `argparse`'s `--help` — travels through the app as an exception: it is thrown into `yield` dependencies at their `yield` (post-`yield` success code such as `db.commit()` is skipped and `except Exception` rollback branches run) and reaches the app's `Exception` / 500 handler and error-reporting middleware as a server error. The process still exits with the requested status. End a successful run by returning from `main`; use `sys.exit` only for usage errors and failures. `SystemExit` raised by a dependency rather than by `main` is unsupported: lifespan shutdown is then best-effort, as on Ctrl-C.

## License

MIT
