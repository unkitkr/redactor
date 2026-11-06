"""JSON syntax locations, retaining scalar spelling and object member order."""

from typing import Literal

from pydantic import BaseModel, NonNegativeInt


class JsonNode(BaseModel, frozen=True, extra="forbid"):
    kind: Literal["object", "array", "string", "number", "boolean", "null"]
    start: NonNegativeInt
    end: NonNegativeInt
    value: str = ""
    # Object children alternate key and value; array children are values.
    children: tuple["JsonNode", ...] = ()
