from pydantic import BaseModel


class MortgageRateResponse(BaseModel):
    value: float
    date: str
