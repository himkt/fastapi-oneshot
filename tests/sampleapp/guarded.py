from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException


def require_api_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
    if x_api_key is None:
        raise HTTPException(status_code=403, detail="missing X-API-Key")


guarded_app = FastAPI(dependencies=[Depends(require_api_key)])
