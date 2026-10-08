from typing import Annotated

from fastapi import Depends
from pydantic import BaseModel


class Item(BaseModel):
    name: str
    tags: "list[Tag]"


class Tag(BaseModel):
    label: str


def get_item() -> Item:
    return Item.model_validate({"name": "widget", "tags": [{"label": "blue"}]})


def main(item: Annotated[Item, Depends(get_item)]) -> None:
    print(item.model_dump_json())
