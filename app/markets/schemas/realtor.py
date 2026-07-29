from datetime import datetime

from pydantic import BaseModel

from .common import BaseResponse


class RealtorSchema(BaseResponse):
    id: int
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    brokerage: str | None = None
    notes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RealtorCreateSchema(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    brokerage: str | None = None
    notes: str | None = None


class RealtorUpdateSchema(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    brokerage: str | None = None
    notes: str | None = None
