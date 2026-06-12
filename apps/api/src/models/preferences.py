from typing import Literal

from pydantic import BaseModel, Field

Typeface = Literal[
    "arizona",
    "literata",
    "bitter",
    "inter",
    "jost",
    "eb-garamond",
    "libre-baskerville",
]


class Preferences(BaseModel):
    typeface: Typeface = "arizona"
    fontSize: int = Field(default=18, ge=10, le=48)
    isSpeedReaderMode: bool = False
