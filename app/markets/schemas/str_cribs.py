from decimal import Decimal

from pydantic import BaseModel

from app.core.serialization import PlainDecimal

from .common import BaseResponse


class StrCribsFeeDetailsSchema(BaseResponse):
    id: int
    sqft: int | None = None
    fee: PlainDecimal | None = None


class StrCribsFeeDetailsCreateSchema(BaseModel):
    sqft: int | None = None
    fee: Decimal | None = None


class StrCribsFeeDetailsUpdateSchema(BaseModel):
    sqft: int | None = None
    fee: Decimal | None = None
