from fastapi import Response


def main() -> Response:
    return Response(status_code=500)
