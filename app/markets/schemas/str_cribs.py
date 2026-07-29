from decimal import Decimal

from pydantic import BaseModel

from .common import BaseResponse


class StrCribsFeeDetailsSchema(BaseResponse):
    id: int
    sqft: int | None = None
    fee: Decimal | None = None


class StrCribsFeeDetailsCreateSchema(BaseModel):
    sqft: int | None = None
    fee: Decimal | None = None


class StrCribsFeeDetailsUpdateSchema(BaseModel):
    sqft: int | None = None
    fee: Decimal | None = None
