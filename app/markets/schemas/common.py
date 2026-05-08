from pydantic import BaseModel


class BaseResponse(BaseModel):
    model_config = {"from_attributes": True}
