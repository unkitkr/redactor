"""HL7 delimiters and complete native segments, including their line endings."""

from pydantic import BaseModel


class Hl7Message(BaseModel, frozen=True, extra="forbid"):
    field: str
    component: str
    repetition: str
    escape: str
    subcomponent: str
    segments: tuple[tuple[str, ...], ...]
    endings: tuple[str, ...]
