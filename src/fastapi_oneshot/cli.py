import argparse
import os
import sys
from pathlib import Path

from fastapi_oneshot.runner import ScriptExit, ScriptLoadError, load_app, run


def split_at_double_dash(args: list[str]) -> tuple[list[str], list[str]]:
    if "--" not in args:
        return args, []
    index = args.index("--")
    return args[:index], args[index + 1 :]


def main() -> None:
    cli_args, script_argv = split_at_double_dash(sys.argv[1:])
    parser = argparse.ArgumentParser(
        prog="fastapi-oneshot",
        usage="%(prog)s SCRIPT --app MODULE:ATTR [-- SCRIPT_ARG ...]",
        description="Run a script's main function with a FastAPI app's dependencies.",
    )
    parser.add_argument(
        "script", type=Path, metavar="SCRIPT", help="script file that defines main"
    )
    parser.add_argument(
        "--app",
        required=True,
        metavar="MODULE:ATTR",
        help="import string of the FastAPI instance, e.g. myapp.main:app",
    )
    args = parser.parse_args(cli_args)

    sys.path.insert(0, os.getcwd())
    try:
        app = load_app(args.app)
        response = run(app, args.script, script_argv)
    except ScriptLoadError as error:
        parser.error(str(error))
    except ScriptExit as error:
        sys.exit(error.code)

    if not response.is_success:
        print(
            f"fastapi-oneshot: request failed with status {response.status_code}",
            file=sys.stderr,
        )
        if response.text:
            print(response.text, file=sys.stderr)
        sys.exit(1)
