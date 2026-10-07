from __future__ import annotations

from pydantic import BaseModel


class ErrorOut(BaseModel):
    detail: str
